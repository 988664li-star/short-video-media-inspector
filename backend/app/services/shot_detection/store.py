"""Persist, expire, and safely expose one shot-detection job's artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any


class ShotDetectionStore:
    """Own cache keys, JSON results, cleanup, and approved asset-path access."""

    def __init__(self, data_path: Path, cache_ttl_seconds: int) -> None:
        self.data_path = data_path
        self.cache_ttl_seconds = cache_ttl_seconds

    def cache_key(
        self,
        aweme_id: str,
        source_url: str,
        scene_threshold: float,
        min_shot_seconds: float,
    ) -> str:
        # 平台 CDN 地址带签名且会频繁变化；同一作品不能因为重新解析到
        # 新 URL 就失去已经落盘的源视频。作品 ID 才是本地素材的稳定标识。
        del source_url
        value = "|".join(
            (
                aweme_id,
                "pyscenedetect-local-source-v2",
                str(scene_threshold),
                str(min_shot_seconds),
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def read_result(self, cache_key: str) -> dict[str, Any] | None:
        result_path = self.data_path / cache_key / "scenes.json"
        source_path = result_path.with_name("source.mp4")
        try:
            if self.is_expired(result_path) or not source_path.is_file():
                return None
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) and isinstance(payload.get("shots"), list) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def write_result(result_path: Path, payload: dict[str, Any]) -> None:
        temporary_path = result_path.with_suffix(".partial")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(result_path)

    def cleanup_expired(self) -> int:
        try:
            jobs = list(self.data_path.iterdir())
        except OSError:
            return 0
        removed = 0
        for job_path in jobs:
            if not job_path.is_dir():
                continue
            try:
                result_path = job_path / "scenes.json"
                if (job_path / ".active").exists():
                    continue
                source_path = job_path / "source.mp4"
                expires_at = result_path if result_path.is_file() else source_path
                if expires_at.is_file() and self.is_expired(expires_at):
                    shutil.rmtree(job_path)
                    removed += 1
            except OSError:
                continue
        return removed

    def get_asset(self, analysis_id: str, relative_path: str) -> Path | None:
        if not re.fullmatch(r"[a-f0-9]{64}", analysis_id):
            return None
        job_path = (self.data_path / analysis_id).resolve()
        candidate_path = (job_path / relative_path).resolve()
        try:
            relative_to_job = candidate_path.relative_to(job_path)
        except ValueError:
            return None
        if not relative_to_job.parts or (
            relative_to_job.as_posix() != "source.mp4"
            and not relative_to_job.parts[0].startswith("scene_")
            and relative_to_job.parts[0] != "storyboard_chunks"
        ):
            return None
        return candidate_path if candidate_path.is_file() else None

    def is_expired(self, result_path: Path) -> bool:
        if self.cache_ttl_seconds <= 0:
            return False
        try:
            return time.time() - result_path.stat().st_mtime > self.cache_ttl_seconds
        except OSError:
            return True

    @staticmethod
    def remove_incomplete(job_path: Path, result_path: Path) -> None:
        if result_path.exists():
            return
        try:
            shutil.rmtree(job_path)
        except OSError:
            pass
