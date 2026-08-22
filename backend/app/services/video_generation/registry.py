"""Registration and capability routing for video generation providers."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    VideoGenerationProvider,
    VideoGenerationProviderError,
    VideoModelProfile,
)


class VideoGenerationRegistry:
    def __init__(self, providers: Iterable[VideoGenerationProvider]) -> None:
        self._providers: dict[str, VideoGenerationProvider] = {}
        self._models: dict[str, tuple[VideoGenerationProvider, VideoModelProfile]] = {}
        for provider in providers:
            if provider.key in self._providers:
                raise ValueError(f"重复的视频供应商：{provider.key}")
            self._providers[provider.key] = provider
            for model in provider.models:
                if model.id in self._models:
                    raise ValueError(f"重复的视频模型：{model.id}")
                self._models[model.id] = (provider, model)

    def resolve(
        self,
        model_id: str,
        *,
        capability: str | None = None,
    ) -> tuple[VideoGenerationProvider, VideoModelProfile]:
        resolved = self._models.get(model_id)
        if resolved is None:
            raise VideoGenerationProviderError(f"未注册的视频模型：{model_id}")
        provider, model = resolved
        if capability and capability not in model.capabilities:
            raise VideoGenerationProviderError(
                f"模型“{model.label}”不支持当前的{capability}任务"
            )
        return provider, model

    def catalog(self, capability: str | None = None) -> list[dict[str, object]]:
        return [
            model.public_dict()
            for _, model in self._models.values()
            if not capability or capability in model.capabilities
        ]
