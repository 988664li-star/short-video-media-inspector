"""SQLite-backed canvas documents and their local asset metadata."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

from .assets import CanvasAssetStorage


EMPTY_DOCUMENT = {
    "nodes": [],
    "edges": [],
    "viewport": {"x": 0, "y": 0, "scale": 0.9},
}


class CanvasProjectNotFoundError(KeyError):
    """Requested canvas project does not exist."""


class CanvasAssetNotFoundError(KeyError):
    """Requested canvas asset does not exist."""


class CanvasProjectService:
    """Store canvas documents in SQLite and each asset in its project's folder."""

    def __init__(self, db_path: Path, data_path: Path) -> None:
        self.db_path = db_path
        self.data_path = data_path
        self.asset_storage = CanvasAssetStorage(data_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_path.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canvas_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    asset_directory TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS canvas_assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES canvas_projects(id)
                );
                CREATE INDEX IF NOT EXISTS canvas_projects_updated_at
                    ON canvas_projects (updated_at DESC);
                CREATE INDEX IF NOT EXISTS canvas_assets_project_id
                    ON canvas_assets (project_id, created_at DESC);
                """
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM canvas_projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._payload(row, include_document=False) for row in rows]

    def create_project(self, name: str) -> dict[str, Any]:
        return self._create_project(name)

    def get_or_create_default_project(self) -> dict[str, Any]:
        """Create the first blank canvas once, even if two browser mounts race."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM canvas_projects ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                return self._payload(row)

            project_id = uuid4().hex
            now = int(time.time() * 1000)
            asset_directory = self._asset_directory(project_id)
            asset_directory.mkdir(parents=True, exist_ok=False)
            connection.execute(
                """
                INSERT INTO canvas_projects (
                    id, name, document_json, asset_directory, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, "未命名画布", json.dumps(EMPTY_DOCUMENT, ensure_ascii=False), str(asset_directory.relative_to(self.data_path)), now, now),
            )
            row = connection.execute(
                "SELECT * FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._payload(row)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise CanvasProjectNotFoundError(project_id)
        return self._payload(row)

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time() * 1000)
        document = {
            "nodes": payload["nodes"],
            "edges": payload["edges"],
            "viewport": payload["viewport"],
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT document_json FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
            if current_row is None:
                raise CanvasProjectNotFoundError(project_id)
            try:
                current_document = json.loads(current_row["document_json"])
            except json.JSONDecodeError:
                current_document = dict(EMPTY_DOCUMENT)
            document = self._preserve_submitted_replacement_state(
                current_document, document
            )
            updated = connection.execute(
                """
                UPDATE canvas_projects
                SET name = ?, document_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload["name"], json.dumps(document, ensure_ascii=False, separators=(",", ":")), now, project_id),
            )
            if updated.rowcount == 0:
                raise CanvasProjectNotFoundError(project_id)
            row = connection.execute(
                "SELECT * FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._payload(row)

    @staticmethod
    def _preserve_submitted_replacement_state(
        current: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        """Prevent a stale browser save from erasing paid provider submissions."""
        merged = copy.deepcopy(incoming)
        current_nodes = {
            node.get("id"): node
            for node in current.get("nodes") or []
            if isinstance(node, dict) and node.get("id")
        }
        incoming_nodes = {
            node.get("id"): node
            for node in merged.get("nodes") or []
            if isinstance(node, dict) and node.get("id")
        }
        protected_output_ids: set[str] = set()
        for node_id, node in current_nodes.items():
            task = node.get("replacement_task")
            if not isinstance(task, dict) or node_id not in incoming_nodes:
                continue
            output_id = task.get("output_shot_collection_node_id")
            output_node = current_nodes.get(output_id)
            has_provider_submission = any(
                version.get("provider_task_id")
                for shot in (output_node or {}).get("shot_assets") or []
                for version in shot.get("replacement_versions") or []
                if isinstance(version, dict)
            )
            if not output_id or not has_provider_submission:
                continue
            protected_output_ids.add(output_id)
            incoming_task_node = incoming_nodes[node_id]
            incoming_task = incoming_task_node.get("replacement_task")
            if not isinstance(incoming_task, dict):
                continue
            if not incoming_task.get("output_shot_collection_node_id"):
                incoming_task["output_shot_collection_node_id"] = output_id
            current_prompts = {
                int(prompt.get("shot_index") or 0): prompt
                for prompt in task.get("shot_prompts") or []
                if isinstance(prompt, dict) and prompt.get("provider_task_id")
            }
            for prompt in incoming_task.get("shot_prompts") or []:
                current_prompt = current_prompts.get(int(prompt.get("shot_index") or 0))
                if current_prompt and not prompt.get("provider_task_id"):
                    prompt.update(copy.deepcopy(current_prompt))
            if incoming_task_node.get("operation", {}).get("status") == "running":
                incoming_task_node["operation"] = copy.deepcopy(node.get("operation") or {})
                incoming_task_node["detail"] = node.get("detail", incoming_task_node.get("detail", ""))

        for output_id in protected_output_ids:
            if output_id not in incoming_nodes:
                restored_output = copy.deepcopy(current_nodes[output_id])
                merged.setdefault("nodes", []).append(restored_output)
                incoming_nodes[output_id] = restored_output
        existing_edge_pairs = {
            (edge.get("source"), edge.get("target"))
            for edge in merged.get("edges") or []
            if isinstance(edge, dict)
        }
        for edge in current.get("edges") or []:
            if not isinstance(edge, dict) or edge.get("target") not in protected_output_ids:
                continue
            pair = (edge.get("source"), edge.get("target"))
            if pair not in existing_edge_pairs:
                merged.setdefault("edges", []).append(copy.deepcopy(edge))
                existing_edge_pairs.add(pair)
        return merged

    def record_replacement_submission(
        self,
        project_id: str,
        *,
        task_node_id: str,
        output_node_id: str,
        shots: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> None:
        """Durably attach provider task IDs before the browser can save again."""
        now = int(time.time() * 1000)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT document_json FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise CanvasProjectNotFoundError(project_id)
            try:
                document = json.loads(row["document_json"])
            except json.JSONDecodeError:
                document = dict(EMPTY_DOCUMENT)
            nodes = list(document.get("nodes") or [])
            task_node = next(
                (node for node in nodes if node.get("id") == task_node_id), None
            )
            if not isinstance(task_node, dict):
                raise CanvasProjectNotFoundError(task_node_id)
            task = task_node.get("replacement_task")
            if not isinstance(task, dict):
                raise CanvasProjectNotFoundError(task_node_id)

            subjects = task.get("subjects") or []
            subject_names = "、".join(
                str(subject.get("source_object_name") or "")
                for subject in subjects
                if isinstance(subject, dict)
            ) or str(task.get("source_object_name") or "替换主体")
            subject_names = subject_names[:160]
            source_object_id = str(task.get("source_object_id") or "object-1")
            result_by_shot = {
                int(result["shot_index"]): result
                for result in results
                if isinstance(result.get("shot_index"), int)
            }
            submitted_shots: list[dict[str, Any]] = []
            for shot in shots:
                shot_index = int(shot["index"])
                result = result_by_shot.get(shot_index)
                if result is None:
                    continue
                result_asset = result.get("result_asset") or {}
                version = {
                    "task_node_id": task_node_id,
                    "source_object_id": source_object_id,
                    "source_object_name": subject_names,
                    "model": str(
                        result.get("model")
                        or (task_node.get("operation") or {}).get("model")
                        or ""
                    ),
                    "provider_task_id": str(result.get("provider_task_id") or ""),
                    "status": "pending" if result.get("status") == "original" else result.get("status", "pending"),
                    "result_asset_id": str(result_asset.get("id") or result.get("result_asset_id") or ""),
                    "result_asset_url": str(result_asset.get("url") or result.get("result_asset_url") or ""),
                    "result_asset_name": str(result_asset.get("filename") or result.get("result_asset_name") or ""),
                    "error": str(result.get("error") or ""),
                }
                submitted_shots.append({
                    **shot,
                    "replacement_versions": [version],
                })

            output_node = next(
                (node for node in nodes if node.get("id") == output_node_id), None
            )
            if not isinstance(output_node, dict):
                output_node = {
                    "id": output_node_id,
                    "kind": "shot_collection",
                    "x": float(task_node.get("x") or 0) + 590,
                    "y": float(task_node.get("y") or 0) + 12,
                    "title": f"替换镜头组 · {subject_names}"[:160],
                    "detail": f"已提交 {len(submitted_shots)} 个镜头任务；节点会自动刷新生成结果",
                    "content": "",
                    "source_node_id": task_node_id,
                    "shot_assets": [],
                }
                nodes.append(output_node)
            existing_shots = {
                int(shot["index"]): shot
                for shot in output_node.get("shot_assets") or []
            }
            for shot in submitted_shots:
                shot_index = int(shot["index"])
                existing = existing_shots.get(shot_index, {})
                existing_versions = [
                    version
                    for version in existing.get("replacement_versions") or []
                    if version.get("task_node_id") != task_node_id
                ]
                existing_shots[shot_index] = {
                    **existing,
                    **shot,
                    "replacement_versions": [*existing_versions, *shot["replacement_versions"]],
                }
            output_node["shot_assets"] = [
                existing_shots[index] for index in sorted(existing_shots)
            ]
            output_node["detail"] = (
                f"已提交 {len(submitted_shots)} 个镜头任务；正在自动刷新生成结果"
            )

            task["output_shot_collection_node_id"] = output_node_id
            for prompt in task.get("shot_prompts") or []:
                result = result_by_shot.get(int(prompt.get("shot_index") or 0))
                if result is None:
                    continue
                prompt["status"] = result.get("status", "pending")
                prompt["provider_task_id"] = str(result.get("provider_task_id") or "")
                result_asset = result.get("result_asset") or {}
                prompt["result_asset_id"] = str(
                    result_asset.get("id") or result.get("result_asset_id") or ""
                )
                prompt["error"] = str(result.get("error") or "")
            task_node["detail"] = (
                f"已提交 {len(submitted_shots)} 个独立镜头任务；结果会自动回写到替换镜头组"
            )
            operation = dict(task_node.get("operation") or {})
            operation.update({
                "status": "succeeded",
                "error": "",
                "message": f"已提交 {len(submitted_shots)} 个独立镜头任务，正在自动刷新结果",
            })
            task_node["operation"] = operation

            edges = list(document.get("edges") or [])
            if not any(
                edge.get("source") == task_node_id and edge.get("target") == output_node_id
                for edge in edges
            ):
                edges.append({
                    "id": f"edge-{uuid4().hex}",
                    "source": task_node_id,
                    "target": output_node_id,
                    "sourceHandle": "output",
                    "targetHandle": "input",
                })
            document["nodes"] = nodes
            document["edges"] = edges
            connection.execute(
                "UPDATE canvas_projects SET document_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(document, ensure_ascii=False, separators=(",", ":")), now, project_id),
            )

    def save_asset(
        self, project_id: str, filename: str, mime_type: str, content: bytes
    ) -> dict[str, Any]:
        self.get_project(project_id)
        asset_id = uuid4().hex
        stored_filename = self.asset_storage.write(project_id, asset_id, filename, content)
        now = int(time.time() * 1000)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO canvas_assets (
                    id, project_id, original_filename, stored_filename, mime_type, bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, project_id, filename, stored_filename, mime_type, len(content), now),
            )
            row = connection.execute(
                "SELECT * FROM canvas_assets WHERE id = ?", (asset_id,)
            ).fetchone()
        return self._asset_payload(row)

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM canvas_assets WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [self._asset_payload(row) for row in rows]

    def get_asset_file(self, project_id: str, asset_id: str) -> tuple[dict[str, Any], Path]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canvas_assets WHERE id = ? AND project_id = ?",
                (asset_id, project_id),
            ).fetchone()
        if row is None:
            raise CanvasAssetNotFoundError(asset_id)
        asset = self._asset_payload(row)
        path = self.asset_storage.path_for(project_id, row["stored_filename"])
        if not path.is_file():
            raise CanvasAssetNotFoundError(asset_id)
        return asset, path

    def _create_project(self, name: str) -> dict[str, Any]:
        project_id = uuid4().hex
        now = int(time.time() * 1000)
        asset_directory = self._asset_directory(project_id)
        asset_directory.mkdir(parents=True, exist_ok=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO canvas_projects (
                    id, name, document_json, asset_directory, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, json.dumps(EMPTY_DOCUMENT, ensure_ascii=False), str(asset_directory.relative_to(self.data_path)), now, now),
            )
            row = connection.execute(
                "SELECT * FROM canvas_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._payload(row)

    def _asset_directory(self, project_id: str) -> Path:
        return self.data_path / project_id / "assets"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _payload(row: sqlite3.Row, *, include_document: bool = True) -> dict[str, Any]:
        payload = {
            "id": row["id"], "name": row["name"], "asset_directory": row["asset_directory"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
        if include_document:
            try:
                document = json.loads(row["document_json"])
            except json.JSONDecodeError:
                document = EMPTY_DOCUMENT
            payload["nodes"] = document.get("nodes", [])
            payload["edges"] = document.get("edges", [])
            payload["viewport"] = document.get("viewport", EMPTY_DOCUMENT["viewport"])
        return payload

    @staticmethod
    def _asset_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "project_id": row["project_id"],
            "filename": row["original_filename"], "mime_type": row["mime_type"],
            "bytes": row["bytes"], "created_at": row["created_at"],
        }
