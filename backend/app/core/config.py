from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_COOKIE_STORE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "douyin_cookie.json"
)
DEFAULT_BACKEND_DATA_PATH = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class Settings:
    app_name: str = "抖音媒体检查台 API"
    api_prefix: str = "/api"
    media_session_ttl_seconds: int = 30 * 60
    max_cookie_size: int = 48 * 1024
    cookie_store_path: Path = Path(
        os.environ.get("DOUYIN_COOKIE_STORE_PATH", DEFAULT_COOKIE_STORE_PATH)
    )
    transcription_model_size: str = os.environ.get("WHISPER_MODEL_SIZE", "small")
    transcription_language: str = os.environ.get("WHISPER_LANGUAGE", "zh")
    transcription_device: str = os.environ.get("WHISPER_DEVICE", "cpu")
    transcription_compute_type: str = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    transcription_cpu_threads: int = int(os.environ.get("WHISPER_CPU_THREADS", "8"))
    transcription_max_media_bytes: int = int(
        os.environ.get("WHISPER_MAX_MEDIA_BYTES", str(100 * 1024 * 1024))
    )
    transcription_model_path: Path = Path(
        os.environ.get(
            "WHISPER_MODEL_PATH", DEFAULT_BACKEND_DATA_PATH / "whisper_models"
        )
    )
    transcription_cache_path: Path = Path(
        os.environ.get(
            "WHISPER_TRANSCRIPT_CACHE_PATH",
            DEFAULT_BACKEND_DATA_PATH / "transcriptions",
        )
    )
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    cors_origin_regex: str = (
        r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)"
        r"(:\d+)?$"
    )


settings = Settings()
