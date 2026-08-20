"""Chinese punctuation restoration using the configured FunASR model."""

from __future__ import annotations

from typing import Any

from backend.app.services.transcription.config import TranscriptionConfig
from backend.app.services.transcription.errors import PunctuationModelUnavailableError
from backend.app.services.transcription.text import TranscriptTextNormalizer


class ChinesePunctuationRestorer:
    """Own the punctuation-model lifecycle and restore only Chinese transcripts."""

    def __init__(
        self,
        config: TranscriptionConfig,
        normalizer: TranscriptTextNormalizer,
    ) -> None:
        self.config = config
        self.normalizer = normalizer
        self._model: Any | None = None

    def restore_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.config.language != "zh":
            return payload
        model = self._get_model()
        segments = payload.get("segments")
        if not isinstance(segments, list):
            segments = []
        restored_segments: list[dict[str, Any]] = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text", "")).strip()
            if text:
                segment = {**segment, "text": self.restore_text(model, text)}
            restored_segments.append(segment)

        payload["segments"] = restored_segments
        if restored_segments:
            payload["text"] = "".join(
                str(segment.get("text", "")) for segment in restored_segments
            )
        elif payload.get("text"):
            payload["text"] = self.restore_text(model, str(payload["text"]))
        payload["punctuation_model"] = self.config.punctuation_model
        return payload

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise PunctuationModelUnavailableError(
                "缺少中文标点模型依赖，请重新安装 backend/requirements.txt"
            ) from exc
        try:
            self._model = AutoModel(
                model=self.config.punctuation_model,
                device=self.config.punctuation_device,
                ncpu=self.config.cpu_threads,
                disable_update=True,
                disable_pbar=True,
            )
        except Exception as exc:
            raise PunctuationModelUnavailableError(
                f"中文标点模型加载失败：{exc}"
            ) from exc
        return self._model

    def restore_text(self, model: Any, text: str) -> str:
        try:
            result = model.generate(input=text)
            restored = result[0].get("text") if result else None
        except Exception as exc:
            raise PunctuationModelUnavailableError(
                f"中文标点恢复失败：{exc}"
            ) from exc
        if not isinstance(restored, str) or not restored.strip():
            raise PunctuationModelUnavailableError("中文标点模型没有返回有效结果")
        return self.normalizer.normalize(restored)
