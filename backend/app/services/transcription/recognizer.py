"""Lazy faster-whisper recognition with a safe CPU fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.app.services.transcription.config import TranscriptionConfig
from backend.app.services.transcription.errors import ModelUnavailableError
from backend.app.services.transcription.text import TranscriptTextNormalizer


logger = logging.getLogger(__name__)


class WhisperRecognizer:
    """Own the local Whisper model lifecycle and timestamped speech recognition."""

    def __init__(
        self,
        config: TranscriptionConfig,
        normalizer: TranscriptTextNormalizer,
    ) -> None:
        self.config = config
        self.normalizer = normalizer
        self._model: Any | None = None
        self._runtime_device = config.device
        self._runtime_compute_type = config.compute_type

    @property
    def runtime_device(self) -> str:
        return self._runtime_device

    @property
    def runtime_compute_type(self) -> str:
        return self._runtime_compute_type

    def transcribe_file(self, media_path: Path, context: str) -> dict[str, Any]:
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
                "text": self.normalizer.normalize(segment.text),
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
                    self.config.device, self.config.compute_type
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
