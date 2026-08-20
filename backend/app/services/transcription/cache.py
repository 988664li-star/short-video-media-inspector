"""Privacy-bounded persistence and cleanup for transcript results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any

from backend.app.services.transcription.text import TranscriptTextNormalizer


class TranscriptCache:
    """Own transcript cache keys, TTL checks, writes, and deletion."""

    def __init__(
        self,
        cache_path: Path,
        cache_ttl_seconds: int,
        normalizer: TranscriptTextNormalizer,
    ) -> None:
        self.cache_path = cache_path
        self.cache_ttl_seconds = cache_ttl_seconds
        self.normalizer = normalizer

    @staticmethod
    def cache_key(
        aweme_id: str,
        model_size: str,
        language: str,
        punctuation_model: str,
    ) -> str:
        value = "|".join((aweme_id, model_size, language, punctuation_model))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def read(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_path / f"{cache_key}.json"
        try:
            if self.is_expired(path):
                path.unlink()
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload.get("text"):
                return None
            payload["text"] = self.normalizer.normalize(str(payload["text"]))
            for segment in payload.get("segments", []):
                if isinstance(segment, dict) and segment.get("text"):
                    segment["text"] = self.normalizer.normalize(str(segment["text"]))
            return payload
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def write(self, cache_key: str, payload: dict[str, Any]) -> None:
        self.cache_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.cache_path / f"{cache_key}.json"
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.chmod(0o600)
        temporary_path.replace(path)

    def cleanup_expired(self) -> int:
        try:
            paths = list(self.cache_path.glob("*.json"))
        except OSError:
            return 0
        removed = 0
        for path in paths:
            try:
                if self.is_expired(path):
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def clear(self) -> int:
        try:
            paths = list(self.cache_path.glob("*.json"))
        except OSError:
            return 0
        removed = 0
        for path in paths:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def is_expired(self, path: Path) -> bool:
        if self.cache_ttl_seconds <= 0:
            return True
        return path.stat().st_mtime < time.time() - self.cache_ttl_seconds
