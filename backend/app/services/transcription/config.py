"""Configuration for the local media-transcription workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptionConfig:
    model_size: str
    language: str
    device: str
    compute_type: str
    cpu_threads: int
    punctuation_model: str
    punctuation_device: str
    max_media_bytes: int
    model_path: Path
    cache_path: Path
    cache_ttl_seconds: int
    vocal_separation_enabled: bool = True
    vocal_separation_model: str = "htdemucs"
    vocal_separation_device: str = "cpu"
    vocal_separation_timeout_seconds: int = 600
