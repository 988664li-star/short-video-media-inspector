"""Configuration for one automatic shot-detection workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShotDetectionConfig:
    data_path: Path
    max_media_bytes: int
    scene_threshold: float
    min_shot_seconds: float
    cache_ttl_seconds: int
    ffmpeg_binary: str
