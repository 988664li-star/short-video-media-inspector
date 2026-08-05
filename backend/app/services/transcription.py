from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import tempfile
import time
from typing import Any

import aiofiles
import httpx

from backend.app.core.config import Settings
from backend.app.services.media import MediaResource


logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Base error exposed by the transcription API."""


class MediaDownloadError(TranscriptionError):
    """The allowlisted upstream media could not be downloaded."""


class ModelUnavailableError(TranscriptionError):
    """The local speech recognition model could not be loaded."""


@dataclass(frozen=True)
class TranscriptionConfig:
    model_size: str
    language: str
    device: str
    compute_type: str
    cpu_threads: int
    max_media_bytes: int
    model_path: Path
    cache_path: Path


class TranscriptionService:
    """Download allowlisted media and transcribe it with one lazy-loaded model."""

    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config
        self._model: Any | None = None
        self._runtime_device = config.device
        self._runtime_compute_type = config.compute_type
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
                max_media_bytes=settings.transcription_max_media_bytes,
                model_path=settings.transcription_model_path,
                cache_path=settings.transcription_cache_path,
            )
        )

    async def transcribe(
        self,
        aweme_id: str,
        resource: MediaResource,
        context: str = "",
    ) -> dict[str, Any]:
        cache_key = self._cache_key(aweme_id)
        async with self._job_lock:
            cached = await asyncio.to_thread(self._read_cache, cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

            started_at = time.perf_counter()
            suffix = ".m4a" if resource.kind == "audio" else ".mp4"
            with tempfile.TemporaryDirectory(prefix="douyin-transcribe-") as temp_dir:
                media_path = Path(temp_dir) / f"media{suffix}"
                await self._download_media(resource, media_path)
                result = await asyncio.to_thread(
                    self._transcribe_file,
                    media_path,
                    context,
                )

            payload = {
                "aweme_id": aweme_id,
                "text": result["text"],
                "segments": result["segments"],
                "language": result["language"],
                "language_probability": result["language_probability"],
                "duration_seconds": result["duration_seconds"],
                "model": self.config.model_size,
                "device": self._runtime_device,
                "compute_type": self._runtime_compute_type,
                "source_kind": resource.kind,
                "cached": False,
                "elapsed_seconds": round(time.perf_counter() - started_at, 2),
            }
            await asyncio.to_thread(self._write_cache, cache_key, payload)
            return payload

    async def _download_media(
        self,
        resource: MediaResource,
        destination: Path,
    ) -> None:
        timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
        try:
            async with httpx.AsyncClient(
                headers=resource.headers,
                follow_redirects=True,
                timeout=timeout,
            ) as client:
                async with client.stream("GET", resource.source_url) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("Content-Length", "0"))
                    if content_length > self.config.max_media_bytes:
                        raise MediaDownloadError("媒体文件过大，暂不支持自动转写")

                    downloaded = 0
                    async with aiofiles.open(destination, "wb") as output:
                        async for chunk in response.aiter_bytes(256 * 1024):
                            downloaded += len(chunk)
                            if downloaded > self.config.max_media_bytes:
                                raise MediaDownloadError(
                                    "媒体文件过大，暂不支持自动转写"
                                )
                            await output.write(chunk)
        except MediaDownloadError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise MediaDownloadError(f"音频读取失败：{exc}") from exc

        if not destination.exists() or destination.stat().st_size == 0:
            raise MediaDownloadError("音频文件为空，无法生成文案")

    def _transcribe_file(self, media_path: Path, context: str) -> dict[str, Any]:
        model = self._get_model()
        try:
            return self._run_model(model, media_path, context)
        except Exception as exc:
            if self._runtime_device != "cpu":
                logger.warning("GPU transcription failed, falling back to CPU: %s", exc)
                self._model = self._create_model("cpu", "int8")
                self._runtime_device = "cpu"
                self._runtime_compute_type = "int8"
                return self._run_model(self._model, media_path, context)
            raise ModelUnavailableError(f"语音识别失败：{exc}") from exc

    def _run_model(
        self,
        model: Any,
        media_path: Path,
        context: str,
    ) -> dict[str, Any]:
        language = self.config.language or None
        context_hint = context[:500].strip()
        initial_prompt = None
        if language == "zh":
            initial_prompt = "以下是普通话短视频口播，请使用简体中文和自然标点。"
            if context_hint:
                initial_prompt += f"视频标题和上下文：{context_hint}"
        segments_generator, info = model.transcribe(
            str(media_path),
            language=language,
            task="transcribe",
            beam_size=5,
            temperature=0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
            hotwords=context_hint or None,
        )
        segments = [
            {
                "start": round(float(segment.start), 2),
                "end": round(float(segment.end), 2),
                "text": self._normalize_text(segment.text),
            }
            for segment in segments_generator
            if segment.text.strip()
        ]
        separator = "" if getattr(info, "language", language) == "zh" else " "
        return {
            "text": separator.join(segment["text"] for segment in segments),
            "segments": segments,
            "language": getattr(info, "language", language) or "unknown",
            "language_probability": round(
                float(getattr(info, "language_probability", 0.0)), 4
            ),
            "duration_seconds": round(float(getattr(info, "duration", 0.0)), 2),
        }

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                self._model = self._create_model(
                    self.config.device,
                    self.config.compute_type,
                )
                self._runtime_device = self.config.device
                self._runtime_compute_type = self.config.compute_type
            except Exception as exc:
                if self.config.device == "cpu":
                    raise ModelUnavailableError(f"语音模型加载失败：{exc}") from exc
                logger.warning("GPU model loading failed, falling back to CPU: %s", exc)
                self._model = self._create_model("cpu", "int8")
                self._runtime_device = "cpu"
                self._runtime_compute_type = "int8"
        return self._model

    def _create_model(self, device: str, compute_type: str) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ModelUnavailableError(
                "缺少 faster-whisper，请先安装 backend/requirements.txt"
            ) from exc

        self.config.model_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return WhisperModel(
            self.config.model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=self.config.cpu_threads,
            download_root=str(self.config.model_path),
        )

    def _normalize_text(self, text: str) -> str:
        punctuation = {"﹑": "，", "､": "，"}
        if self.config.language == "zh":
            punctuation[","] = "，"
        return text.strip().translate(str.maketrans(punctuation))

    def _cache_key(self, aweme_id: str) -> str:
        value = "|".join(
            (
                aweme_id,
                self.config.model_size,
                self.config.language,
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.config.cache_path / f"{cache_key}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload.get("text"):
                return None
            payload["text"] = self._normalize_text(str(payload["text"]))
            for segment in payload.get("segments", []):
                if isinstance(segment, dict) and segment.get("text"):
                    segment["text"] = self._normalize_text(str(segment["text"]))
            return payload
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, cache_key: str, payload: dict[str, Any]) -> None:
        self.config.cache_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.config.cache_path / f"{cache_key}.json"
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
