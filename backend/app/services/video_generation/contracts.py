"""Provider-neutral contracts for asynchronous video generation and editing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO, Literal, Protocol


VideoTaskStatus = Literal["queued", "running", "succeeded", "failed"]


class VideoGenerationProviderError(RuntimeError):
    """A configured video provider rejected or could not complete a request."""


class VideoAssetPublisherError(RuntimeError):
    """A source or reference asset could not be published for provider access."""


class VideoAssetPublisher(Protocol):
    def upload(
        self,
        project_id: str,
        file_handle: BinaryIO,
        size: int,
        filename: str,
        content_type: str,
    ) -> tuple[str, str]: ...

    def presign_download(self, object_key: str) -> str: ...


@dataclass(frozen=True)
class VideoModelProfile:
    id: str
    provider: str
    remote_model: str
    label: str
    capabilities: frozenset[str]
    min_duration_seconds: float = 4
    max_duration_seconds: float = 15

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "capabilities": sorted(self.capabilities),
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
        }


@dataclass(frozen=True)
class VideoEditRequest:
    prompt: str
    source_video_url: str
    reference_image_urls: tuple[str, ...]
    duration_seconds: int
    aspect_ratio: str
    generate_audio: bool = False
    watermark: bool = False


@dataclass(frozen=True)
class VideoProviderContext:
    project_id: str
    shot_index: int
    source_asset_id: str = ""
    source_asset_name: str = ""
    source_upload_seconds: float = 0


@dataclass(frozen=True)
class VideoTaskSnapshot:
    provider: str
    model: str
    provider_task_id: str
    status: VideoTaskStatus
    result_url: str = ""
    error: str = ""
    error_code: str = ""
    request_id: str = ""


class VideoGenerationProvider(Protocol):
    key: str
    models: tuple[VideoModelProfile, ...]

    async def submit(
        self,
        model: VideoModelProfile,
        request: VideoEditRequest,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot: ...

    async def refresh(
        self,
        model: VideoModelProfile,
        provider_task_id: str,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot: ...
