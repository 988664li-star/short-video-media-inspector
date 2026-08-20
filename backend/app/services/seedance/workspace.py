"""SQLite-backed material bindings and opt-in Seedance task submission.

The browser uploads local files to Ark Files API.  SQLite stores only the Ark
``file_id`` bindings, so material selection survives reloads while fresh
download URLs are resolved immediately before an explicit video generation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from typing import Any
from uuid import uuid4

import httpx

from .object_storage import ObjectStorageError, SeedanceObjectStorage


SEEDANCE_MINI_MODEL = "doubao-seedance-2-0-mini-260615"
SEEDANCE_STANDARD_MODEL = "doubao-seedance-2-0-260128"
SEEDANCE_FAST_MODEL = "doubao-seedance-2-0-fast-260128"
SUPPORTED_SEEDANCE_MODELS = frozenset(
    {
        SEEDANCE_MINI_MODEL,
        SEEDANCE_STANDARD_MODEL,
        SEEDANCE_FAST_MODEL,
    }
)
logger = logging.getLogger(__name__)
GPT_IMAGE_ANCHOR_MODEL_SUFFIX = " [clean-montage-v2]"


class SeedanceWorkspaceError(RuntimeError):
    """The saved test workspace is incomplete or cannot be read."""


class SeedanceConfigurationError(SeedanceWorkspaceError):
    """A manual submission was requested without server-side Ark credentials."""


class SeedanceProviderError(SeedanceWorkspaceError):
    """Ark rejected a manually submitted task or status query."""


class SeedanceWorkspaceService:
    """Own test-workspace persistence and explicit Ark task requests."""

    def __init__(
        self,
        db_path: Path,
        api_key: str,
        api_url: str,
        files_api_url: str,
        file_max_bytes: int,
        object_storage: SeedanceObjectStorage,
        shot_detection_data_path: Path | None = None,
        ffmpeg_binary: str = "ffmpeg",
        image_api_url: str = "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        image_model: str = "doubao-seedream-5-0-260128",
        gpt_image_api_key: str = "",
        gpt_image_edits_url: str = "https://dm-fox.rjj.cc/codex/v1/images/edits",
        gpt_image_model: str = "gpt-image-2",
    ) -> None:
        self.db_path = db_path
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.files_api_url = files_api_url.rstrip("/")
        self.file_max_bytes = file_max_bytes
        self.object_storage = object_storage
        self.shot_detection_data_path = shot_detection_data_path
        self.ffmpeg_binary = ffmpeg_binary
        self.image_api_url = image_api_url.rstrip("/")
        self.image_model = image_model
        self.gpt_image_api_key = gpt_image_api_key
        self.gpt_image_edits_url = gpt_image_edits_url.rstrip("/")
        self.gpt_image_model = gpt_image_model
        self._segment_lock = asyncio.Lock()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS replica_workspaces (
                    analysis_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL DEFAULT '',
                    bindings_json TEXT NOT NULL DEFAULT '[]',
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ark_files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT '',
                    bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'processing',
                    download_url TEXT NOT NULL DEFAULT '',
                    storage_object_key TEXT NOT NULL DEFAULT '',
                    expire_at INTEGER,
                    error_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS replica_prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS seedance_tasks (
                    local_task_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    segment_id INTEGER,
                    segment_start_ms INTEGER,
                    segment_end_ms INTEGER,
                    provider_task_id TEXT,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS seedance_tasks_analysis_id
                    ON seedance_tasks (analysis_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS seedance_segment_media (
                    analysis_id TEXT NOT NULL,
                    segment_id INTEGER NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    video_file_id TEXT NOT NULL,
                    contact_sheet_file_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (analysis_id, segment_id)
                );

                CREATE TABLE IF NOT EXISTS seedance_visual_anchors (
                    analysis_id TEXT NOT NULL,
                    segment_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    anchor_file_id TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (analysis_id, segment_id)
                );

                CREATE TABLE IF NOT EXISTS seedance_shot_visual_anchors (
                    analysis_id TEXT NOT NULL,
                    segment_id INTEGER NOT NULL,
                    shot_order INTEGER NOT NULL,
                    scene_id INTEGER NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    source_frame_path TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    anchor_file_id TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (analysis_id, segment_id, shot_order)
                );

                CREATE TABLE IF NOT EXISTS ark_api_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    request_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    status_code INTEGER,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ark_api_events_analysis_id
                    ON ark_api_events (analysis_id, created_at DESC, id DESC);
                """
            )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(seedance_tasks)")
            }
            for name, definition in (
                ("segment_id", "INTEGER"),
                ("segment_start_ms", "INTEGER"),
                ("segment_end_ms", "INTEGER"),
            ):
                if name not in task_columns:
                    connection.execute(f"ALTER TABLE seedance_tasks ADD COLUMN {name} {definition}")
            file_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(ark_files)")
            }
            if "storage_object_key" not in file_columns:
                connection.execute(
                    "ALTER TABLE ark_files ADD COLUMN storage_object_key TEXT NOT NULL DEFAULT ''"
                )
        self.object_storage.ensure_bucket()

    def get_workspace(self, analysis_id: str) -> dict[str, Any]:
        self._validate_analysis_id(analysis_id)
        with self._connect() as connection:
            workspace = connection.execute(
                "SELECT * FROM replica_workspaces WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()
            tasks = connection.execute(
                "SELECT * FROM seedance_tasks WHERE analysis_id = ? ORDER BY created_at DESC",
                (analysis_id,),
            ).fetchall()
            ark_events = connection.execute(
                "SELECT * FROM ark_api_events WHERE analysis_id = ? ORDER BY created_at DESC, id DESC LIMIT 30",
                (analysis_id,),
            ).fetchall()
            anchors = connection.execute(
                "SELECT * FROM seedance_visual_anchors WHERE analysis_id = ? ORDER BY segment_id",
                (analysis_id,),
            ).fetchall()
            shot_anchors = connection.execute(
                "SELECT * FROM seedance_shot_visual_anchors WHERE analysis_id = ? ORDER BY segment_id, shot_order",
                (analysis_id,),
            ).fetchall()
        return {
            "analysis_id": analysis_id,
            "workspace": self._workspace_payload(workspace),
            "tasks": [self._task_payload(task) for task in tasks],
            "ark_events": [self._ark_event_payload(event) for event in ark_events],
            "anchors": [self._anchor_payload(anchor) for anchor in anchors],
            "shot_anchors": [self._shot_anchor_payload(anchor) for anchor in shot_anchors],
        }

    def save_workspace(self, analysis_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_analysis_id(analysis_id)
        model = str(payload.get("model") or SEEDANCE_MINI_MODEL)
        if model not in SUPPORTED_SEEDANCE_MODELS:
            raise SeedanceWorkspaceError("请选择工作台提供的 Seedance 2.0 系列模型")
        prompt = str(payload.get("prompt") or "")
        bindings = payload.get("bindings")
        if not isinstance(bindings, list):
            raise SeedanceWorkspaceError("素材绑定格式不正确")
        now = int(time.time())
        encoded_bindings = json.dumps(bindings, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT version, prompt FROM replica_workspaces WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            version = int(previous["version"]) + 1 if previous else 1
            connection.execute(
                """
                INSERT INTO replica_workspaces
                    (analysis_id, model, prompt, bindings_json, version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id) DO UPDATE SET
                    model = excluded.model,
                    prompt = excluded.prompt,
                    bindings_json = excluded.bindings_json,
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (analysis_id, model, prompt, encoded_bindings, version, now),
            )
            if previous is None or previous["prompt"] != prompt:
                connection.execute(
                    """
                    INSERT INTO replica_prompt_versions
                        (analysis_id, version, prompt, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (analysis_id, version, prompt, now),
                )
        return self.get_workspace(analysis_id)

    async def build_request_plan(
        self, analysis_id: str, segment_id: int | None = None
    ) -> dict[str, Any]:
        workspace = self.get_workspace(analysis_id)["workspace"]
        if workspace is None:
            raise SeedanceWorkspaceError("请先保存替换方案和素材绑定")
        prompt = workspace["prompt"].strip()
        if not prompt:
            raise SeedanceWorkspaceError("请先生成或填写测试提示词")

        media = await self._ensure_segment_media(analysis_id)
        if segment_id is not None:
            media = [item for item in media if int(item["segment_id"]) == segment_id]
            if not media:
                raise SeedanceWorkspaceError(f"分段 {segment_id:02d} 不存在")
        anchor_by_segment = self._anchors_by_segment(analysis_id)
        planned: list[dict[str, Any]] = []
        for segment in media:
            segment_id = int(segment["segment_id"])
            anchor = anchor_by_segment.get(segment_id)
            if not (
                anchor
                and anchor["status"] in {"succeeded", "uploaded"}
                and anchor["anchor_file_id"]
            ):
                raise SeedanceWorkspaceError(
                    f"分段 {segment_id:02d} 尚未完成合并分镜图的图片锚点处理"
                )
            if anchor["status"] != "uploaded" and anchor["model"] != self._anchor_model_name:
                raise SeedanceWorkspaceError(
                    f"分段 {segment_id:02d} 的锚点图不符合当前处理规则；请用 GPT Image 2 重新编辑或上传人工处理后的干净拼图"
                )
            video_url = await self._resolve_file_download_url(
                analysis_id, segment["video_file_id"], f"分段 {segment_id:02d} 原视频"
            )
            anchor_urls = [await self._resolve_file_download_url(
                analysis_id, anchor["anchor_file_id"], f"分段 {segment_id:02d} 合并分镜锚点图"
            )]
            segment_prompt = self._segment_video_prompt(prompt, segment)
            planned.append(
                self._request_plan_item(
                    workspace["model"],
                    segment_prompt,
                    video_url,
                    anchor_urls,
                    segment,
                )
            )
        return {"segments": planned}

    @staticmethod
    def _request_plan_item(
        model: str,
        prompt: str,
        video_url: str,
        image_urls: list[str],
        segment: dict[str, Any],
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "video_url", "role": "reference_video", "video_url": {"url": video_url}},
        ]
        content.extend(
            {
                "type": "image_url",
                "role": "reference_image",
                "image_url": {"url": url},
            }
            for url in image_urls
        )
        return {
            "segment": {
                "segment_id": int(segment["segment_id"]),
                "start_ms": int(segment["start_ms"]),
                "end_ms": int(segment["end_ms"]),
            },
            "request": {
                "model": model,
                "content": content,
                "generate_audio": False,
                "watermark": False,
                "duration": -1,
                "ratio": "adaptive",
            },
        }

    @staticmethod
    def _segment_video_prompt(prompt: str, segment: dict[str, Any]) -> str:
        return (
            f"本次只严格编辑 @视频1 的分段 {int(segment['segment_id']):02d}"
            f"（{int(segment['start_ms']) / 1000:.2f}–{int(segment['end_ms']) / 1000:.2f} 秒）。"
            "@图片1 是该分段全部镜头合并后的最终视觉锚点图，按网格顺序对应视频中的各个镜头。"
            "严格以其中已确认的目标产品外观、状态、手部交互和光照作为本分段的一致性参考；"
            "它不是新的场景，也不是多件产品。不要延伸、补写或重排其他分段。\n\n"
            f"{prompt}"
        )

    async def generate_anchor_image(
        self, analysis_id: str, segment_id: int, *, force: bool = False
    ) -> dict[str, Any]:
        """Explicitly edit one merged storyboard image per video segment.

        One request covers all representative shots in a <=15-second segment,
        keeping the image-edit stage affordable while giving the video model one
        visual consistency reference for that segment.
        """
        if not self.gpt_image_api_key:
            raise SeedanceConfigurationError("未配置 GPT_IMAGE_API_KEY，无法调用 GPT Image 2 图片编辑")
        workspace = self.get_workspace(analysis_id)["workspace"]
        if workspace is None:
            raise SeedanceWorkspaceError("请先保存替换方案和产品素材")
        segment = next(
            (item for item in self._load_storyboard_segments(analysis_id) if int(item["segment_id"]) == segment_id),
            None,
        )
        if segment is None:
            raise SeedanceWorkspaceError(f"分段 {segment_id:02d} 不存在")
        existing = self._anchors_by_segment(analysis_id).get(segment_id)
        if (
            existing
            and existing["status"] == "succeeded"
            and existing["model"] == self._anchor_model_name
            and not force
        ):
            return self.get_workspace(analysis_id)
        products = self._selected_product_contexts(analysis_id, workspace["bindings"])
        if not products:
            raise SeedanceWorkspaceError("请先勾选产品并上传至少一张产品参考图")
        product_file_ids = [file_id for product in products for file_id in product["file_ids"]]
        if len(product_file_ids) > 15:
            raise SeedanceWorkspaceError("GPT Image 2 单次最多使用 15 张产品参考图")
        source_path = self._ensure_anchor_source_image(analysis_id, segment)
        if not source_path.is_file():
            raise SeedanceWorkspaceError("原始分镜关键帧不存在，请重新执行自动分镜")
        prompt = self._anchor_prompt(segment, products)
        image_size = self._gpt_image_size(source_path)
        product_files = [await self.refresh_file(analysis_id, file_id) for file_id in product_file_ids]
        request_payload = {
            "model": self.gpt_image_model,
            "prompt": prompt,
            "size": image_size,
            "quality": "high",
            "response_format": "b64_json",
            "images": [
                {"index": 1, "role": "source_contact_sheet", "filename": source_path.name},
                *[
                    {"index": index, "role": "target_product", "file_id": file_id}
                    for index, file_id in enumerate(product_file_ids, start=2)
                ],
            ],
        }
        operation = "gpt-image.anchor.submit"
        self._log_ark_request(operation, analysis_id, self.gpt_image_edits_url, request_payload)
        try:
            multipart_images: list[tuple[str, tuple[str, bytes, str]]] = [
                ("image", (source_path.name, source_path.read_bytes(), "image/jpeg"))
            ]
            for file_payload in product_files:
                image_bytes = await self._download_file_bytes(str(file_payload["download_url"]))
                mime_type = str(file_payload.get("mime_type") or "image/png")
                multipart_images.append(
                    ("image", (str(file_payload["filename"]), image_bytes, mime_type))
                )
            form = {
                "model": self.gpt_image_model,
                "prompt": prompt,
                "size": image_size,
                "quality": "high",
                "response_format": "b64_json",
            }
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    self.gpt_image_edits_url,
                    headers={"Authorization": f"Bearer {self.gpt_image_api_key}"},
                    data=form,
                    files=multipart_images,
                )
            body = self._response_json(response)
            self._log_ark_response(operation, analysis_id, response.status_code, body)
            error = "" if not response.is_error else self._provider_error_message(body, response.status_code)
            self._record_ark_event(
                analysis_id, operation, "POST", self.gpt_image_edits_url, request_payload,
                body if isinstance(body, dict) else {"raw": body}, response.status_code, error,
            )
            if response.is_error:
                self._save_anchor(analysis_id, segment_id, prompt, "failed", "", request_payload, body if isinstance(body, dict) else {"raw": body}, error)
                raise SeedanceProviderError(error)
            anchor_file_id = self._store_gpt_image_result(analysis_id, segment, body)
            self._save_anchor(analysis_id, segment_id, prompt, "succeeded", anchor_file_id, request_payload, body if isinstance(body, dict) else {"raw": body}, "")
        except httpx.HTTPError as exc:
            error = f"GPT Image 2 图片编辑请求失败：{exc}"
            self._record_ark_event(analysis_id, operation, "POST", self.gpt_image_edits_url, request_payload, {}, None, error)
            self._save_anchor(analysis_id, segment_id, prompt, "failed", "", request_payload, {}, error)
            raise SeedanceProviderError(error) from exc
        return self.get_workspace(analysis_id)

    def get_anchor_image_previews(self, analysis_id: str) -> dict[str, Any]:
        """Return the exact non-billable GPT Image 2 plan for each segment."""
        self._validate_analysis_id(analysis_id)
        workspace = self.get_workspace(analysis_id)["workspace"]
        if workspace is None:
            raise SeedanceWorkspaceError("请先保存替换方案和产品素材")
        products = self._selected_product_contexts(analysis_id, workspace["bindings"])
        previews: list[dict[str, Any]] = []
        for segment in self._load_storyboard_segments(analysis_id):
            inputs: list[dict[str, Any]] = [
                {
                    "image_index": 1,
                    "kind": "source_contact_sheet",
                    "label": f"图1：分段 {int(segment['segment_id']):02d} 的干净合并分镜图（无文字、无间隔）",
                    "source_frame_path": self._ensure_anchor_source_image(analysis_id, segment).relative_to(
                        self._analysis_job_path(analysis_id)
                    ).as_posix(),
                }
            ]
            image_index = 2
            for product in products:
                for file_id in product["file_ids"]:
                    inputs.append(
                        {
                            "image_index": image_index,
                            "kind": "target_product",
                            "candidate_id": product["candidate_id"],
                            "file_id": file_id,
                            "label": f"图{image_index}：目标产品参考图",
                        }
                    )
                    image_index += 1
            ready = bool(products)
            previews.append(
                {
                    "segment_id": int(segment["segment_id"]),
                    "start_ms": int(segment["start_ms"]),
                    "end_ms": int(segment["end_ms"]),
                    "source_frame_path": self._ensure_anchor_source_image(analysis_id, segment).relative_to(
                        self._analysis_job_path(analysis_id)
                    ).as_posix(),
                    "prompt": self._anchor_prompt(segment, products) if ready else "",
                    "inputs": inputs,
                    "ready": ready,
                    "message": "" if ready else "请先勾选产品并绑定至少一张产品参考图，再查看图片处理提示词。",
                    "model": self.gpt_image_model,
                }
            )
        return {"previews": previews}

    async def bind_anchor_image(self, analysis_id: str, segment_id: int, file_id: str) -> dict[str, Any]:
        """Use a user-provided processed contact sheet instead of GPT Image 2."""
        file = await self.refresh_file(analysis_id, file_id)
        if not file["mime_type"].startswith("image/"):
            raise SeedanceWorkspaceError("视觉锚点必须是图片文件")
        request_payload = {"source": "user_upload", "file_id": file_id}
        self._save_anchor(
            analysis_id, segment_id,
            "用户上传的已处理合并分镜锚点图。",
            "uploaded",
            file_id,
            request_payload,
            {"file_id": file_id, "filename": file["filename"]},
            "",
        )
        return self.get_workspace(analysis_id)

    async def _ensure_segment_media(self, analysis_id: str) -> list[dict[str, Any]]:
        segments = self._load_storyboard_segments(analysis_id)
        async with self._segment_lock:
            cached = self._segment_media_by_id(analysis_id)
            missing = [segment for segment in segments if int(segment["segment_id"]) not in cached]
            if not missing:
                return [{**segment, **cached[int(segment["segment_id"])]} for segment in segments]
            source_path = self._analysis_job_path(analysis_id) / "source.mp4"
            if not source_path.is_file():
                raise SeedanceWorkspaceError("自动分镜的原视频已过期，请重新识别后再生成分段素材")
            with tempfile.TemporaryDirectory(prefix="seedance-segments-") as temp_dir:
                temp_root = Path(temp_dir)
                for segment in missing:
                    segment_id = int(segment["segment_id"])
                    contact_sheet = self._safe_analysis_asset(analysis_id, str(segment["contact_sheet"]))
                    if not contact_sheet.is_file():
                        raise SeedanceWorkspaceError(f"分段 {segment_id:02d} 的分镜联系图不存在")
                    clip_path = temp_root / f"segment-{segment_id:03d}.mp4"
                    await asyncio.to_thread(
                        self._cut_segment_video,
                        source_path,
                        clip_path,
                        int(segment["start_ms"]),
                        int(segment["end_ms"]),
                    )
                    video_file_id = self._store_local_asset(
                        analysis_id, clip_path, "video/mp4", clip_path.name
                    )
                    sheet_file_id = self._store_local_asset(
                        analysis_id, contact_sheet, "image/jpeg", f"segment-{segment_id:03d}-storyboard.jpg"
                    )
                    self._save_segment_media(
                        analysis_id, segment, video_file_id, sheet_file_id
                    )
                    cached[segment_id] = {
                        "video_file_id": video_file_id,
                        "contact_sheet_file_id": sheet_file_id,
                    }
        return [{**segment, **cached[int(segment["segment_id"])]} for segment in segments]

    def _cut_segment_video(self, source: Path, output: Path, start_ms: int, end_ms: int) -> None:
        duration = max(0.1, (end_ms - start_ms) / 1000)
        command = [
            self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start_ms / 1000:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(output),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise SeedanceWorkspaceError("未安装 FFmpeg，无法导出分段视频") from exc
        except subprocess.CalledProcessError as exc:
            raise SeedanceWorkspaceError(f"导出分段视频失败：{exc.stderr.strip() or '未知错误'}") from exc

    def _store_local_asset(self, analysis_id: str, path: Path, content_type: str, filename: str) -> str:
        size = path.stat().st_size
        if size <= 0:
            raise SeedanceWorkspaceError("生成的分段素材为空")
        try:
            with path.open("rb") as source:
                file_id, object_key = self.object_storage.upload(
                    analysis_id, source, size, filename, content_type
                )
            self._upsert_ark_file(
                {
                    "id": file_id, "filename": filename, "mime_type": content_type,
                    "bytes": size, "status": "active", "download_url": self.object_storage.presign_download(object_key),
                },
                object_key,
            )
            return file_id
        except ObjectStorageError as exc:
            raise SeedanceWorkspaceError(str(exc)) from exc

    def _analysis_job_path(self, analysis_id: str) -> Path:
        self._validate_analysis_id(analysis_id)
        if self.shot_detection_data_path is None:
            raise SeedanceWorkspaceError("未配置自动分镜素材目录")
        root = self.shot_detection_data_path.resolve()
        target = (root / analysis_id).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SeedanceWorkspaceError("分镜素材目录无效") from exc
        return target

    def _safe_analysis_asset(self, analysis_id: str, relative_path: str) -> Path:
        root = self._analysis_job_path(analysis_id)
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SeedanceWorkspaceError("分镜素材路径无效") from exc
        return target

    def _load_storyboard_segments(self, analysis_id: str) -> list[dict[str, Any]]:
        script_path = self._analysis_job_path(analysis_id) / "storyboard_chunks" / "scripts.json"
        try:
            payload = json.loads(script_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SeedanceWorkspaceError("请先完成分段分镜脚本") from exc
        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(raw_segments, list) or not raw_segments:
            raise SeedanceWorkspaceError("分段分镜脚本没有可用片段")
        segments: list[dict[str, Any]] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            try:
                segment_id = int(raw["segment_id"])
                start_ms = int(raw["start_ms"])
                end_ms = int(raw["end_ms"])
                contact_sheet = str(raw["contact_sheet"])
            except (KeyError, TypeError, ValueError):
                continue
            if segment_id > 0 and end_ms > start_ms and contact_sheet:
                segments.append(
                    {
                        "segment_id": segment_id,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "contact_sheet": contact_sheet,
                    }
                )
        segments.sort(key=lambda item: item["segment_id"])
        if not segments:
            raise SeedanceWorkspaceError("分段分镜脚本格式不完整")
        return segments

    def _load_storyboard_shots(self, analysis_id: str) -> list[dict[str, Any]]:
        manifest_path = self._analysis_job_path(analysis_id) / "storyboard_chunks" / "manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SeedanceWorkspaceError("请先完成分段分镜脚本") from exc
        chunks = payload.get("chunks") if isinstance(payload, dict) else None
        if not isinstance(chunks, list):
            raise SeedanceWorkspaceError("分段镜头清单不可用")
        shots: list[dict[str, Any]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict) or not isinstance(chunk.get("shots"), list):
                continue
            try:
                segment_id = int(chunk["segment_id"])
            except (KeyError, TypeError, ValueError):
                continue
            for raw in chunk["shots"]:
                if not isinstance(raw, dict):
                    continue
                frames = raw.get("frame_paths")
                if not isinstance(frames, list) or not frames:
                    continue
                try:
                    shot_order = int(raw["order"])
                    scene_id = int(raw["scene_id"])
                    start_ms = int(raw["start_ms"])
                    end_ms = int(raw["end_ms"])
                    source_frame_path = str(frames[len(frames) // 2])
                except (KeyError, TypeError, ValueError):
                    continue
                if segment_id > 0 and shot_order > 0 and end_ms > start_ms and source_frame_path:
                    shots.append(
                        {
                            "segment_id": segment_id,
                            "shot_order": shot_order,
                            "scene_id": scene_id,
                            "start_ms": start_ms,
                            "end_ms": end_ms,
                            "source_frame_path": source_frame_path,
                        }
                    )
        shots.sort(key=lambda item: (item["segment_id"], item["shot_order"]))
        if not shots:
            raise SeedanceWorkspaceError("分段镜头清单没有可编辑的关键帧")
        return shots

    @property
    def _anchor_model_name(self) -> str:
        return f"{self.gpt_image_model}{GPT_IMAGE_ANCHOR_MODEL_SUFFIX}"

    def _ensure_anchor_source_image(
        self, analysis_id: str, segment: dict[str, Any]
    ) -> Path:
        """Create the model input montage separately from the analysis contact sheet.

        It uses one representative frame per shot and a GPT Image-supported
        portrait/landscape canvas. Captions and gutters are deliberately omitted.
        """
        segment_id = int(segment["segment_id"])
        relative_output = (
            Path("storyboard_chunks")
            / f"segment_{segment_id:03d}"
            / "anchor_input_clean_v2.jpg"
        )
        output = self._safe_analysis_asset(analysis_id, relative_output.as_posix())
        if output.is_file() and output.stat().st_size > 0:
            return output
        frames = [
            self._safe_analysis_asset(analysis_id, str(shot["source_frame_path"]))
            for shot in self._load_storyboard_shots(analysis_id)
            if int(shot["segment_id"]) == segment_id
        ]
        if not frames:
            raise SeedanceWorkspaceError(f"分段 {segment_id:02d} 没有可用于拼图的镜头关键帧")
        if any(not frame.is_file() for frame in frames):
            raise SeedanceWorkspaceError("原始镜头关键帧不存在，请重新执行自动分镜")
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise SeedanceWorkspaceError("缺少 Pillow，无法生成图片编辑输入拼图") from exc
        with Image.open(frames[0]) as first:
            first_width, first_height = first.size
        canvas_size = (1024, 1536) if first_height >= first_width else (1536, 1024)
        columns, rows = self._montage_grid(
            len(frames),
            first_width / max(1, first_height),
            canvas_size[0] / canvas_size[1],
        )
        canvas = Image.new("RGB", canvas_size)
        cell_width = canvas_size[0] // columns
        cell_height = canvas_size[1] // rows
        for index, frame_path in enumerate(frames):
            row, column = divmod(index, columns)
            left = column * cell_width
            top = row * cell_height
            right = canvas_size[0] if column == columns - 1 else left + cell_width
            bottom = canvas_size[1] if row == rows - 1 else top + cell_height
            with Image.open(frame_path) as raw_image:
                fitted = ImageOps.fit(
                    raw_image.convert("RGB"),
                    (right - left, bottom - top),
                    method=Image.Resampling.LANCZOS,
                )
            canvas.paste(fitted, (left, top))
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = output.with_suffix(".partial")
        canvas.save(temporary, format="JPEG", quality=95, optimize=True)
        temporary.replace(output)
        return output

    @staticmethod
    def _montage_grid(
        frame_count: int, frame_ratio: float, canvas_ratio: float
    ) -> tuple[int, int]:
        if frame_count <= 0:
            raise SeedanceWorkspaceError("没有可用于拼图的镜头关键帧")
        candidates: list[tuple[float, int, int, bool]] = []
        for columns in range(1, frame_count + 1):
            rows = math.ceil(frame_count / columns)
            montage_ratio = columns * frame_ratio / rows
            aspect_penalty = abs(
                math.log(max(montage_ratio, 0.01) / max(canvas_ratio, 0.01))
            )
            candidates.append((aspect_penalty, columns, rows, columns * rows == frame_count))
        exact = [item for item in candidates if item[3]]
        _, columns, rows, _ = min(exact or candidates)
        return columns, rows

    @staticmethod
    def _gpt_image_size(source_path: Path) -> str:
        try:
            from PIL import Image
        except ImportError as exc:
            raise SeedanceWorkspaceError("缺少 Pillow，无法读取图片编辑输入尺寸") from exc
        with Image.open(source_path) as image:
            width, height = image.size
        return "1024x1536" if height >= width else "1536x1024"

    def _find_storyboard_shot(
        self, analysis_id: str, segment_id: int, shot_order: int
    ) -> dict[str, Any]:
        if shot_order <= 0:
            raise SeedanceWorkspaceError("请指定需要处理的镜头编号")
        shot = next(
            (
                item
                for item in self._load_storyboard_shots(analysis_id)
                if int(item["segment_id"]) == segment_id and int(item["shot_order"]) == shot_order
            ),
            None,
        )
        if shot is None:
            raise SeedanceWorkspaceError("镜头编号不存在，请刷新图片处理预览")
        return shot

    def _segment_media_by_id(self, analysis_id: str) -> dict[int, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM seedance_segment_media WHERE analysis_id = ?", (analysis_id,)
            ).fetchall()
        return {
            int(row["segment_id"]): {
                "video_file_id": str(row["video_file_id"]),
                "contact_sheet_file_id": str(row["contact_sheet_file_id"]),
            }
            for row in rows
        }

    def _save_segment_media(
        self, analysis_id: str, segment: dict[str, Any], video_file_id: str, contact_sheet_file_id: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO seedance_segment_media
                    (analysis_id, segment_id, start_ms, end_ms, video_file_id, contact_sheet_file_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id, segment_id) DO UPDATE SET
                    start_ms = excluded.start_ms, end_ms = excluded.end_ms,
                    video_file_id = excluded.video_file_id,
                    contact_sheet_file_id = excluded.contact_sheet_file_id
                """,
                (
                    analysis_id, int(segment["segment_id"]), int(segment["start_ms"]), int(segment["end_ms"]),
                    video_file_id, contact_sheet_file_id, int(time.time()),
                ),
            )

    def _anchors_by_segment(self, analysis_id: str) -> dict[int, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM seedance_visual_anchors WHERE analysis_id = ?", (analysis_id,)
            ).fetchall()
        return {int(row["segment_id"]): self._anchor_payload(row) for row in rows}

    def _shot_anchors_by_key(self, analysis_id: str) -> dict[tuple[int, int], dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM seedance_shot_visual_anchors WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
        return {
            (int(row["segment_id"]), int(row["shot_order"])): self._shot_anchor_payload(row)
            for row in rows
        }

    def _selected_product_contexts(
        self, analysis_id: str, bindings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        playbook_path = self._analysis_job_path(analysis_id) / "replica_playbook.json"
        try:
            playbook = json.loads(playbook_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SeedanceWorkspaceError("请先生成替换方案") from exc
        candidates = (
            playbook.get("playbook", {}).get("replacement_candidates", [])
            if isinstance(playbook, dict)
            else []
        )
        candidate_map = {
            str(item.get("candidate_id")): item
            for item in candidates if isinstance(item, dict) and item.get("type") == "product"
        }
        products: list[dict[str, Any]] = []
        for binding in bindings:
            if not isinstance(binding, dict) or not binding.get("enabled"):
                continue
            candidate = candidate_map.get(str(binding.get("candidate_id") or ""))
            if candidate is None:
                continue
            assets = binding.get("assets") if isinstance(binding.get("assets"), list) else []
            file_ids = [
                str(asset.get("file_id"))
                for asset in sorted(assets, key=lambda item: int(item.get("slot_index", 0)) if isinstance(item, dict) else 0)
                if isinstance(asset, dict) and str(asset.get("file_id") or "")
            ]
            if not file_ids:
                continue
            products.append(
                {
                    "candidate_id": str(candidate.get("candidate_id") or ""),
                    "source_description": str(candidate.get("source_description") or "源视频中的产品"),
                    "target_description": str(binding.get("target_description") or "目标产品"),
                    "file_ids": file_ids,
                }
            )
        return products

    @staticmethod
    def _anchor_prompt(segment: dict[str, Any], products: list[dict[str, Any]]) -> str:
        definitions = []
        edits = []
        image_index = 2
        for ordinal, product in enumerate(products, start=1):
            count = len(product["file_ids"])
            refs = "、".join(f"图{index}" for index in range(image_index, image_index + count))
            definitions.append(
                f"将{refs}中展示的同一目标产品定义为产品{ordinal}：{product['target_description']}。"
            )
            edits.append(f"将“{product['source_description']}”替换为产品{ordinal}")
            image_index += count
        return (
            f"图1是原视频分段 {int(segment['segment_id']):02d} 的干净多镜头拼图，按时间顺序排列。"
            "严格编辑图1，保留每个子画面的顺序、人物、手部动作、背景、机位、透视和光线；"
            "不得改变拼图画布比例，不得添加间隔、边框、字幕、文字、水印或 Logo，不要把子画面合并成一张新场景。"
            + "".join(definitions)
            + "在图1的每一个子画面中" + "；".join(edits)
            + "。替换后的产品在所有子画面中必须是同一件产品，外观、颜色、结构和细节一致；"
            "亮灯、支撑、握持等状态需符合各子画面的原有交互。"
        )

    @staticmethod
    def _shot_anchor_prompt(shot: dict[str, Any], products: list[dict[str, Any]]) -> str:
        definitions: list[str] = []
        edits: list[str] = []
        image_index = 2
        for ordinal, product in enumerate(products, start=1):
            refs = "、".join(
                f"图{index}" for index in range(image_index, image_index + len(product["file_ids"]))
            )
            definitions.append(
                f"图{refs.removeprefix('图')}展示同一目标产品，定义为产品{ordinal}：{product['target_description']}。"
            )
            edits.append(f"将“{product['source_description']}”替换为产品{ordinal}")
            image_index += len(product["file_ids"])
        return (
            f"严格编辑图1（分段 {int(shot['segment_id']):02d} 的镜头 {int(shot['shot_order']):02d} 原始关键帧）。"
            + "".join(definitions)
            + "仅" + "；".join(edits)
            + "。保留图1中的手部姿势和接触点、人物、背景、镜头构图、透视、光线、喷雾或发光效果、字幕与未提及物体；"
            "不要重绘场景，不要改变任何未替换物体，不要新增文字、水印或 Logo。"
        )

    async def _download_file_bytes(self, url: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SeedanceProviderError(f"下载产品参考图失败：{exc}") from exc
        if not response.content:
            raise SeedanceProviderError("下载的产品参考图为空")
        return response.content

    def _store_gpt_image_result(self, analysis_id: str, segment: dict[str, Any], body: Any) -> str:
        if not isinstance(body, dict):
            raise SeedanceProviderError("GPT Image 2 没有返回有效结果")
        data = body.get("data")
        first = data[0] if isinstance(data, list) and data else None
        encoded = first.get("b64_json") if isinstance(first, dict) else None
        if not isinstance(encoded, str) or not encoded:
            raise SeedanceProviderError("GPT Image 2 未返回 b64_json 图片数据")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise SeedanceProviderError("GPT Image 2 返回的图片数据无法解码") from exc
        if not image_bytes:
            raise SeedanceProviderError("GPT Image 2 返回了空图片")
        with tempfile.TemporaryDirectory(prefix="gpt-image-anchor-") as temp_dir:
            output = Path(temp_dir) / f"segment-{int(segment['segment_id']):03d}-anchor.png"
            output.write_bytes(image_bytes)
            return self._store_local_asset(analysis_id, output, "image/png", output.name)

    @staticmethod
    def _image_output_url(body: Any) -> str:
        if not isinstance(body, dict):
            return ""
        data = body.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return ""
        url = data[0].get("url")
        return str(url) if isinstance(url, str) and url.startswith(("http://", "https://")) else ""

    async def _store_generated_image(self, analysis_id: str, segment_id: int, output_url: str) -> str:
        with tempfile.TemporaryDirectory(prefix="seedream-anchor-") as temp_dir:
            output = Path(temp_dir) / f"segment-{segment_id:03d}-anchor.jpg"
            try:
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    async with client.stream("GET", output_url) as response:
                        response.raise_for_status()
                        with output.open("wb") as destination:
                            async for chunk in response.aiter_bytes():
                                destination.write(chunk)
            except httpx.HTTPError as exc:
                raise SeedanceProviderError(f"下载图片模型结果失败：{exc}") from exc
            return self._store_local_asset(
                analysis_id, output, "image/jpeg", output.name
            )

    def _save_shot_anchor(
        self,
        analysis_id: str,
        shot: dict[str, Any],
        prompt: str,
        status: str,
        anchor_file_id: str,
        request_payload: dict[str, Any],
        response_payload: Any,
        error_message: str,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO seedance_shot_visual_anchors
                    (analysis_id, segment_id, shot_order, scene_id, start_ms, end_ms, source_frame_path,
                     model, prompt, status, anchor_file_id, request_json, response_json, error_message,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id, segment_id, shot_order) DO UPDATE SET
                    scene_id = excluded.scene_id, start_ms = excluded.start_ms, end_ms = excluded.end_ms,
                    source_frame_path = excluded.source_frame_path, model = excluded.model,
                    prompt = excluded.prompt, status = excluded.status, anchor_file_id = excluded.anchor_file_id,
                    request_json = excluded.request_json, response_json = excluded.response_json,
                    error_message = excluded.error_message, updated_at = excluded.updated_at
                """,
                (
                    analysis_id, int(shot["segment_id"]), int(shot["shot_order"]), int(shot["scene_id"]),
                    int(shot["start_ms"]), int(shot["end_ms"]), str(shot["source_frame_path"]),
                    self.gpt_image_model, prompt, status, anchor_file_id,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(response_payload if isinstance(response_payload, dict) else {"raw": response_payload}, ensure_ascii=False, separators=(",", ":")),
                    error_message, now, now,
                ),
            )

    def _save_anchor(
        self,
        analysis_id: str,
        segment_id: int,
        prompt: str,
        status: str,
        anchor_file_id: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        error_message: str,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO seedance_visual_anchors
                    (analysis_id, segment_id, model, prompt, status, anchor_file_id,
                     request_json, response_json, error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id, segment_id) DO UPDATE SET
                    model = excluded.model, prompt = excluded.prompt, status = excluded.status,
                    anchor_file_id = excluded.anchor_file_id, request_json = excluded.request_json,
                    response_json = excluded.response_json, error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    analysis_id,
                    segment_id,
                    "manual_upload" if status == "uploaded" else self._anchor_model_name,
                    prompt,
                    status,
                    anchor_file_id,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(response_payload, ensure_ascii=False, separators=(",", ":")),
                    error_message, now, now,
                ),
            )

    async def submit_task(self, analysis_id: str, segment_id: int | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise SeedanceConfigurationError(
                "未配置 ARK_API_KEY；请求已保存在工作台，但不会提交或产生费用"
            )
        workspace = self.get_workspace(analysis_id)["workspace"]
        if workspace and segment_id is None:
            raise SeedanceWorkspaceError("请明确选择一个分段后再提交；分段模式不会批量提交")
        try:
            plan = await self.build_request_plan(analysis_id, segment_id)
        except SeedanceWorkspaceError as exc:
            self._record_ark_event(
                analysis_id, "seedance.submit.preflight", "POST", self.api_url,
                {"model": "saved-workspace"}, {}, None, f"请求未发送：{exc}",
            )
            raise
        planned_segments = plan["segments"]
        if not planned_segments:
            raise SeedanceWorkspaceError("没有可提交的 Seedance 分段")
        segments = planned_segments
        for item in segments:
            request_payload = item["request"]
            segment = item["segment"]
            local_task_id = uuid4().hex
            now = int(time.time())
            operation = "seedance.submit.segment"
            self._log_ark_request(operation, analysis_id, self.api_url, request_payload)
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=request_payload,
                    )
                body = self._response_json(response)
                self._log_ark_response(operation, analysis_id, response.status_code, body)
                error = "" if not response.is_error else self._provider_error_message(body, response.status_code)
                self._record_ark_event(
                    analysis_id, operation, "POST", self.api_url, request_payload,
                    body if isinstance(body, dict) else {"raw": body}, response.status_code, error,
                )
                provider_task_id = body.get("id") if isinstance(body, dict) else None
                task_status = str(body.get("status") or "failed") if isinstance(body, dict) else "failed"
                self._save_task(
                    local_task_id, analysis_id,
                    provider_task_id if isinstance(provider_task_id, str) else None,
                    task_status, request_payload, body if isinstance(body, dict) else {"raw": body},
                    error, now, segment,
                )
            except httpx.HTTPError as exc:
                message = f"Seedance 请求失败：{exc}"
                self._record_ark_event(
                    analysis_id, operation, "POST", self.api_url, request_payload, {}, None, message,
                )
                self._save_task(local_task_id, analysis_id, None, "failed", request_payload, {}, message, now, segment)
                logger.exception("Ark request transport error [%s analysis_id=%s]: %s", operation, analysis_id, exc)
        return self.get_workspace(analysis_id)

    async def refresh_task(self, analysis_id: str, local_task_id: str) -> dict[str, Any]:
        self._validate_analysis_id(analysis_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM seedance_tasks WHERE local_task_id = ? AND analysis_id = ?",
                (local_task_id, analysis_id),
            ).fetchone()
        if row is None:
            raise SeedanceWorkspaceError("测试任务不存在")
        provider_task_id = row["provider_task_id"]
        if not provider_task_id:
            raise SeedanceWorkspaceError("该任务没有可查询的方舟任务标识")
        if not self.api_key:
            raise SeedanceConfigurationError("未配置 ARK_API_KEY，无法刷新方舟任务状态")
        try:
            refresh_url = f"{self.api_url}/{provider_task_id}"
            self._log_ark_request("seedance.task.refresh", analysis_id, refresh_url, {})
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    refresh_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            body = self._response_json(response)
            self._log_ark_response("seedance.task.refresh", analysis_id, response.status_code, body)
            self._record_ark_event(
                analysis_id, "seedance.task.refresh", "GET", refresh_url, {},
                body if isinstance(body, dict) else {"raw": body}, response.status_code,
                "" if not response.is_error else self._provider_error_message(body, response.status_code),
            )
            if response.is_error:
                raise SeedanceProviderError(self._provider_error_message(body, response.status_code))
        except httpx.HTTPError as exc:
            self._record_ark_event(
                analysis_id, "seedance.task.refresh", "GET", f"{self.api_url}/{provider_task_id}", {}, {}, None, str(exc),
            )
            logger.exception("Ark request transport error [seedance.task.refresh analysis_id=%s]: %s", analysis_id, exc)
            raise SeedanceProviderError(f"Seedance 状态查询失败：{exc}") from exc
        self._save_task(
            row["local_task_id"],
            analysis_id,
            provider_task_id,
            str(body.get("status") or row["status"]),
            json.loads(row["request_json"]),
            body if isinstance(body, dict) else {"raw": body},
            "",
            int(row["created_at"]),
        )
        return self.get_workspace(analysis_id)

    def _save_task(
        self,
        local_task_id: str,
        analysis_id: str,
        provider_task_id: str | None,
        task_status: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        error_message: str,
        created_at: int,
        segment: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO seedance_tasks
                    (local_task_id, analysis_id, segment_id, segment_start_ms, segment_end_ms, provider_task_id, model, status, request_json,
                     response_json, error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(local_task_id) DO UPDATE SET
                    provider_task_id = excluded.provider_task_id,
                    status = excluded.status,
                    response_json = excluded.response_json,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    local_task_id,
                    analysis_id,
                    int(segment["segment_id"]) if segment else None,
                    int(segment["start_ms"]) if segment else None,
                    int(segment["end_ms"]) if segment else None,
                    provider_task_id,
                    str(request_payload.get("model") or SEEDANCE_MINI_MODEL),
                    task_status,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(response_payload, ensure_ascii=False, separators=(",", ":")),
                    error_message,
                    created_at,
                    now,
                ),
            )

    async def upload_file(self, analysis_id: str, upload: Any) -> dict[str, Any]:
        filename = str(getattr(upload, "filename", "") or "upload")
        content_type = str(getattr(upload, "content_type", "") or "application/octet-stream")
        file_handle = getattr(upload, "file", None)
        if file_handle is None:
            raise SeedanceWorkspaceError("未收到要上传的文件")
        file_handle.seek(0, 2)
        size = file_handle.tell()
        file_handle.seek(0)
        if size <= 0:
            raise SeedanceWorkspaceError("不能上传空文件")
        if size > self.file_max_bytes:
            raise SeedanceWorkspaceError("文件超过测试对象存储的 512MB 上限")
        request_payload = {
            "bucket": self.object_storage.bucket,
            "file": {"filename": filename, "mime_type": content_type, "bytes": size},
        }
        storage_url = f"object-storage://{self.object_storage.bucket}"
        self._log_ark_request("object_storage.upload", analysis_id, storage_url, request_payload)
        try:
            file_id, object_key = self.object_storage.upload(
                analysis_id, file_handle, size, filename, content_type
            )
            body = {
                "id": file_id, "filename": filename, "mime_type": content_type,
                "bytes": size, "status": "active", "object_key": object_key,
                "download_url": self.object_storage.presign_download(object_key),
            }
            self._log_ark_response("object_storage.upload", analysis_id, 200, body)
            self._record_ark_event(
                analysis_id, "object_storage.upload", "PUT", storage_url, request_payload, body, 200, "",
            )
        except ObjectStorageError as exc:
            self._record_ark_event(analysis_id, "object_storage.upload", "PUT", storage_url, request_payload, {}, None, str(exc))
            raise SeedanceWorkspaceError(str(exc)) from exc
        self._upsert_ark_file(body, object_key)
        return self._ark_file_payload(body)

    async def list_files(self, analysis_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ark_files WHERE storage_object_key <> '' ORDER BY created_at DESC"
            ).fetchall()
        files: list[dict[str, Any]] = []
        for row in rows:
            try:
                files.append(await self.refresh_file(analysis_id, str(row["id"])))
            except SeedanceWorkspaceError:
                continue
        return {"files": files}

    async def refresh_file(self, analysis_id: str, file_id: str) -> dict[str, Any]:
        if not file_id:
            raise SeedanceWorkspaceError("测试素材标识无效")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ark_files WHERE id = ? AND storage_object_key <> ''", (file_id,)
            ).fetchone()
        if row is None:
            raise SeedanceWorkspaceError("测试对象存储中不存在该素材，请重新上传")
        object_key = str(row["storage_object_key"])
        request_url = f"object-storage://{self.object_storage.bucket}/{object_key}"
        self._log_ark_request("object_storage.retrieve", analysis_id, request_url, {})
        try:
            size, content_type = self.object_storage.describe(object_key)
            body = {
                "id": file_id, "filename": str(row["filename"]), "mime_type": content_type,
                "bytes": size, "status": "active", "object_key": object_key,
                "download_url": self.object_storage.presign_download(object_key),
            }
            self._log_ark_response("object_storage.retrieve", analysis_id, 200, body)
            self._record_ark_event(
                analysis_id, "object_storage.retrieve", "HEAD", request_url, {}, body, 200, "",
            )
        except ObjectStorageError as exc:
            self._record_ark_event(analysis_id, "object_storage.retrieve", "HEAD", request_url, {}, {}, None, str(exc))
            raise SeedanceWorkspaceError(str(exc)) from exc
        self._upsert_ark_file(body, object_key)
        return self._ark_file_payload(body)

    async def _resolve_file_download_url(self, analysis_id: str, file_id: str, label: str) -> str:
        file_payload = await self.refresh_file(analysis_id, file_id)
        if file_payload["status"] != "active":
            raise SeedanceWorkspaceError(f"{label}仍在对象存储处理中，请等待状态变为 active")
        url = file_payload["download_url"]
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise SeedanceWorkspaceError(f"{label}没有可用的对象存储下载地址")
        return url

    def _upsert_ark_file(self, payload: dict[str, Any], object_key: str = "") -> None:
        file_id = str(payload["id"])
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ark_files (id, filename, mime_type, bytes, status, download_url, storage_object_key, expire_at, error_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename, mime_type = excluded.mime_type,
                    bytes = excluded.bytes, status = excluded.status,
                    download_url = excluded.download_url,
                    storage_object_key = CASE WHEN excluded.storage_object_key <> '' THEN excluded.storage_object_key ELSE ark_files.storage_object_key END,
                    expire_at = excluded.expire_at,
                    error_json = excluded.error_json, updated_at = excluded.updated_at
                """,
                (
                    file_id, str(payload.get("filename") or ""), str(payload.get("mime_type") or ""),
                    int(payload.get("bytes") or 0), str(payload.get("status") or "processing"),
                    str(payload.get("download_url") or ""), object_key, payload.get("expire_at"),
                    json.dumps(payload.get("error") or {}, ensure_ascii=False),
                    int(payload.get("created_at") or now), now,
                ),
            )

    def _record_ark_event(
        self,
        analysis_id: str,
        operation: str,
        method: str,
        url: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        status_code: int | None,
        error_message: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ark_api_events
                    (analysis_id, operation, method, url, request_json, response_json,
                     status_code, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id, operation, method, url,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(response_payload, ensure_ascii=False, separators=(",", ":")),
                    status_code, error_message, int(time.time()),
                ),
            )

    @staticmethod
    def _log_ark_request(operation: str, analysis_id: str, url: str, payload: dict[str, Any]) -> None:
        logger.info(
            "Ark request [%s analysis_id=%s url=%s]: %s",
            operation, analysis_id, url,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _log_ark_response(operation: str, analysis_id: str, status_code: int, payload: Any) -> None:
        logger.info(
            "Ark response [%s analysis_id=%s http_status=%s]: %s",
            operation, analysis_id, status_code,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        )

    @staticmethod
    def _ark_file_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(payload.get("id") or ""), "filename": str(payload.get("filename") or ""),
            "mime_type": str(payload.get("mime_type") or ""), "bytes": int(payload.get("bytes") or 0),
            "status": str(payload.get("status") or "processing"),
            "download_url": str(payload.get("download_url") or ""), "expire_at": payload.get("expire_at"),
            "created_at": int(payload.get("created_at") or 0), "error": payload.get("error") or {},
        }

    @staticmethod
    def _response_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"message": response.text[:500]}

    @staticmethod
    def _provider_error_message(body: Any, status_code: int) -> str:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    return f"Seedance 返回 {status_code}：{message}"
            for key in ("message", "detail"):
                if isinstance(body.get(key), str):
                    return f"Seedance 返回 {status_code}：{body[key]}"
        return f"Seedance 返回 HTTP {status_code}"

    @staticmethod
    def _validate_analysis_id(analysis_id: str) -> None:
        if len(analysis_id) != 64 or any(char not in "0123456789abcdef" for char in analysis_id):
            raise SeedanceWorkspaceError("分镜任务标识无效")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _workspace_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        try:
            bindings = json.loads(row["bindings_json"])
        except json.JSONDecodeError:
            bindings = []
        return {
            "analysis_id": row["analysis_id"],
            "model": row["model"],
            "prompt": row["prompt"],
            "bindings": bindings if isinstance(bindings, list) else [],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _task_payload(row: sqlite3.Row) -> dict[str, Any]:
        try:
            response = json.loads(row["response_json"])
        except json.JSONDecodeError:
            response = {}
        return {
            "local_task_id": row["local_task_id"],
            "provider_task_id": row["provider_task_id"],
            "segment_id": row["segment_id"],
            "segment_start_ms": row["segment_start_ms"],
            "segment_end_ms": row["segment_end_ms"],
            "model": row["model"],
            "status": row["status"],
            "request": json.loads(row["request_json"]),
            "response": response,
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _anchor_payload(row: sqlite3.Row) -> dict[str, Any]:
        try:
            response = json.loads(row["response_json"])
        except json.JSONDecodeError:
            response = {}
        return {
            "segment_id": int(row["segment_id"]),
            "model": str(row["model"]),
            "prompt": str(row["prompt"]),
            "status": str(row["status"]),
            "anchor_file_id": str(row["anchor_file_id"]),
            "response": response,
            "error_message": str(row["error_message"]),
            "updated_at": int(row["updated_at"]),
        }

    @staticmethod
    def _shot_anchor_payload(row: sqlite3.Row) -> dict[str, Any]:
        try:
            response = json.loads(row["response_json"])
        except json.JSONDecodeError:
            response = {}
        return {
            "segment_id": int(row["segment_id"]),
            "shot_order": int(row["shot_order"]),
            "scene_id": int(row["scene_id"]),
            "start_ms": int(row["start_ms"]),
            "end_ms": int(row["end_ms"]),
            "source_frame_path": str(row["source_frame_path"]),
            "model": str(row["model"]),
            "prompt": str(row["prompt"]),
            "status": str(row["status"]),
            "anchor_file_id": str(row["anchor_file_id"]),
            "response": response,
            "error_message": str(row["error_message"]),
            "updated_at": int(row["updated_at"]),
        }

    @staticmethod
    def _ark_event_payload(row: sqlite3.Row) -> dict[str, Any]:
        try:
            request = json.loads(row["request_json"])
        except json.JSONDecodeError:
            request = {}
        try:
            response = json.loads(row["response_json"])
        except json.JSONDecodeError:
            response = {}
        return {
            "id": row["id"],
            "operation": row["operation"],
            "method": row["method"],
            "url": row["url"],
            "request": request,
            "response": response,
            "status_code": row["status_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
        }
