"""SQLite-backed canvas documents and their local asset metadata."""

from __future__ import annotations

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
