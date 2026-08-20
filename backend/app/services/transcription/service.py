"""Orchestrate transcript download, recognition, punctuation, and caching."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import tempfile
import time
from typing import Any

from backend.app.core.config import Settings
from backend.app.services.media import MediaResource
from backend.app.services.transcription.cache import TranscriptCache
from backend.app.services.transcription.config import TranscriptionConfig
from backend.app.services.transcription.downloader import TranscriptionMediaDownloader
from backend.app.services.transcription.errors import MediaDownloadError
from backend.app.services.transcription.punctuation import ChinesePunctuationRestorer
from backend.app.services.transcription.recognizer import WhisperRecognizer
from backend.app.services.transcription.separator import VocalSeparator
from backend.app.services.transcription.text import TranscriptTextNormalizer


logger = logging.getLogger(__name__)


class TranscriptionService:
    """Coordinate local speech recognition while keeping components independent."""

    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config
        self._normalizer = TranscriptTextNormalizer(config.language)
        self._downloader = TranscriptionMediaDownloader(config.max_media_bytes)
        self._recognizer = WhisperRecognizer(config, self._normalizer)
        self._separator = VocalSeparator(config)
        self._punctuation = ChinesePunctuationRestorer(config, self._normalizer)
        self._cache = TranscriptCache(
            config.cache_path, config.cache_ttl_seconds, self._normalizer
        )
        self._job_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "TranscriptionService":
        return cls(
            TranscriptionConfig(
                model_size=settings.transcription_model_size,
                language=settings.transcription_language,
                device=settings.transcription_device,
                compute_type=settings.transcription_compute_type,
                cpu_threads=settings.transcription_cpu_threads,
                punctuation_model=settings.punctuation_model,
                punctuation_device=settings.punctuation_device,
                max_media_bytes=settings.transcription_max_media_bytes,
                model_path=settings.transcription_model_path,
                cache_path=settings.transcription_cache_path,
                cache_ttl_seconds=settings.transcription_cache_ttl_seconds,
                vocal_separation_enabled=settings.vocal_separation_enabled,
                vocal_separation_model=settings.vocal_separation_model,
                vocal_separation_device=settings.vocal_separation_device,
                vocal_separation_timeout_seconds=settings.vocal_separation_timeout_seconds,
            )
        )

    async def transcribe(
        self,
        aweme_id: str,
        resource: MediaResource,
        context: str = "",
    ) -> dict[str, Any]:
        cache_key = self._cache.cache_key(
            aweme_id,
            self.config.model_size,
            self.config.language,
            self.config.punctuation_model,
        )
        async with self._job_lock:
            await asyncio.to_thread(self.cleanup_expired_cache)
            cached = await asyncio.to_thread(self._cache.read, cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

            started_at = time.perf_counter()
            suffix = ".m4a" if resource.kind == "audio" else ".mp4"
            with tempfile.TemporaryDirectory(prefix="douyin-transcribe-") as temp_dir:
                media_path = Path(temp_dir) / f"media{suffix}"
                await self._downloader.download(resource, media_path)
                result = await asyncio.to_thread(
                    self._recognizer.transcribe_file, media_path, context
                )
            payload = self._build_payload(
                aweme_id, result, resource.kind, started_at, include_cache_ttl=True
            )
            payload = await asyncio.to_thread(self._punctuation.restore_payload, payload)
            await asyncio.to_thread(self._cache.write, cache_key, payload)
            return payload

    async def transcribe_local_file(
        self,
        aweme_id: str,
        media_path: Path,
        context: str = "",
        vocals_path: Path | None = None,
    ) -> dict[str, Any]:
        """Transcribe an already downloaded source video without another network download."""
        if not media_path.is_file() or media_path.stat().st_size == 0:
            raise MediaDownloadError("分镜源视频不存在，无法生成口播")
        async with self._job_lock:
            started_at = time.perf_counter()
            recognition_path = media_path
            audio_source = "original"
            separation_error = ""
            if self.config.vocal_separation_enabled:
                target_path = vocals_path or media_path.with_suffix(".vocals.mp3")
                try:
                    recognition_path = await asyncio.to_thread(
                        self._separator.extract_vocals, media_path, target_path
                    )
                    audio_source = "vocal_stem"
                except Exception as exc:
                    separation_error = str(exc)
                    logger.warning(
                        "人声分离失败，降级使用原始音轨转写：%s", separation_error
                    )
            result = await asyncio.to_thread(
                self._recognizer.transcribe_file, recognition_path, context
            )
            payload = self._build_payload(
                aweme_id, result, "video", started_at, include_cache_ttl=False
            )
            payload["audio_source"] = audio_source
            if separation_error:
                payload["audio_separation_error"] = separation_error
            return await asyncio.to_thread(self._punctuation.restore_payload, payload)

    def cleanup_expired_cache(self) -> int:
        return self._cache.cleanup_expired()

    def clear_cache(self) -> int:
        return self._cache.clear()

    def _build_payload(
        self,
        aweme_id: str,
        result: dict[str, Any],
        source_kind: str,
        started_at: float,
        include_cache_ttl: bool,
    ) -> dict[str, Any]:
        payload = {
            "aweme_id": aweme_id,
            "text": result["text"],
            "segments": result["segments"],
            "language": result["language"],
            "language_probability": result["language_probability"],
            "duration_seconds": result["duration_seconds"],
            "model": self.config.model_size,
            "punctuation_model": self.config.punctuation_model,
            "device": self._recognizer.runtime_device,
            "compute_type": self._recognizer.runtime_compute_type,
            "source_kind": source_kind,
            "cached": False,
            "elapsed_seconds": round(time.perf_counter() - started_at, 2),
        }
        if include_cache_ttl:
            payload["cache_ttl_seconds"] = self.config.cache_ttl_seconds
        return payload
