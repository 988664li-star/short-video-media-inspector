from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_BACKEND_DATA_PATH = Path(__file__).resolve().parents[2] / "data"
DEFAULT_BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


load_dotenv(DEFAULT_BACKEND_ENV_PATH)


@dataclass(frozen=True)
class Settings:
    app_name: str = "抖音媒体检查台 API"
    api_prefix: str = "/api"
    max_cookie_size: int = 48 * 1024
    transcription_model_size: str = os.environ.get("WHISPER_MODEL_SIZE", "small")
    transcription_language: str = os.environ.get("WHISPER_LANGUAGE", "zh")
    transcription_device: str = os.environ.get("WHISPER_DEVICE", "cpu")
    transcription_compute_type: str = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    transcription_cpu_threads: int = int(os.environ.get("WHISPER_CPU_THREADS", "8"))
    punctuation_model: str = os.environ.get("PUNCTUATION_MODEL", "ct-punc")
    punctuation_device: str = os.environ.get("PUNCTUATION_DEVICE", "cpu")
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
    transcription_cache_ttl_seconds: int = int(
        os.environ.get("TRANSCRIPTION_CACHE_TTL_SECONDS", str(30 * 60))
    )
    vocal_separation_enabled: bool = os.environ.get(
        "VOCAL_SEPARATION_ENABLED", "true"
    ).lower() in {"1", "true", "yes", "on"}
    vocal_separation_model: str = os.environ.get(
        "VOCAL_SEPARATION_MODEL", "htdemucs"
    )
    vocal_separation_device: str = os.environ.get(
        "VOCAL_SEPARATION_DEVICE", "cpu"
    )
    vocal_separation_timeout_seconds: int = int(
        os.environ.get("VOCAL_SEPARATION_TIMEOUT_SECONDS", "600")
    )
    shot_detection_data_path: Path = Path(
        os.environ.get(
            "SHOT_DETECTION_DATA_PATH",
            DEFAULT_BACKEND_DATA_PATH / "shot_detection",
        )
    )
    shot_detection_max_media_bytes: int = int(
        os.environ.get("SHOT_DETECTION_MAX_MEDIA_BYTES", str(200 * 1024 * 1024))
    )
    shot_detection_scene_threshold: float = float(
        os.environ.get("SHOT_DETECTION_SCENE_THRESHOLD", "27")
    )
    shot_detection_min_shot_seconds: float = float(
        os.environ.get("SHOT_DETECTION_MIN_SHOT_SECONDS", "0.5")
    )
    shot_detection_cache_ttl_seconds: int = int(
        os.environ.get("SHOT_DETECTION_CACHE_TTL_SECONDS", str(7 * 24 * 60 * 60))
    )
    shot_detection_ffmpeg_binary: str = os.environ.get(
        "SHOT_DETECTION_FFMPEG_BINARY", "ffmpeg"
    )
    replica_workspace_db_path: Path = Path(
        os.environ.get(
            "REPLICA_WORKSPACE_DB_PATH",
            DEFAULT_BACKEND_DATA_PATH / "replica_workspaces.sqlite3",
        )
    )
    replica_projects_db_path: Path = Path(
        os.environ.get(
            "REPLICA_PROJECTS_DB_PATH",
            DEFAULT_BACKEND_DATA_PATH / "replica_projects.sqlite3",
        )
    )
    canvas_projects_db_path: Path = Path(
        os.environ.get(
            "CANVAS_PROJECTS_DB_PATH",
            DEFAULT_BACKEND_DATA_PATH / "canvas_projects.sqlite3",
        )
    )
    canvas_projects_data_path: Path = Path(
        os.environ.get(
            "CANVAS_PROJECTS_DATA_PATH",
            DEFAULT_BACKEND_DATA_PATH / "canvas_projects",
        )
    )
    canvas_asset_max_bytes: int = int(
        os.environ.get("CANVAS_ASSET_MAX_BYTES", str(200 * 1024 * 1024))
    )
    seedance_api_key: str = os.environ.get("ARK_API_KEY", "")
    seedance_api_url: str = os.environ.get(
        "VOLCENGINE_ARK_CONTENT_GENERATION_URL",
        "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
    )
    seedream_api_url: str = os.environ.get(
        "VOLCENGINE_ARK_IMAGE_GENERATION_URL",
        "https://ark.cn-beijing.volces.com/api/v3/images/generations",
    )
    seedream_model: str = os.environ.get(
        "SEEDREAM_MODEL", "doubao-seedream-5-0-260128"
    )
    ark_files_api_url: str = os.environ.get(
        "VOLCENGINE_ARK_FILES_API_URL",
        "https://ark.cn-beijing.volces.com/api/v3/files",
    )
    ark_file_max_bytes: int = int(
        os.environ.get("VOLCENGINE_ARK_FILE_MAX_BYTES", str(512 * 1024 * 1024))
    )
    seedance_object_storage_endpoint: str = os.environ.get(
        "SEEDANCE_OBJECT_STORAGE_ENDPOINT", ""
    )
    seedance_object_storage_access_key: str = os.environ.get(
        "SEEDANCE_OBJECT_STORAGE_ACCESS_KEY", ""
    )
    seedance_object_storage_secret_key: str = os.environ.get(
        "SEEDANCE_OBJECT_STORAGE_SECRET_KEY", ""
    )
    seedance_object_storage_bucket: str = os.environ.get(
        "SEEDANCE_OBJECT_STORAGE_BUCKET", "f2-seedance-test"
    )
    seedance_object_storage_presign_seconds: int = int(
        os.environ.get("SEEDANCE_OBJECT_STORAGE_PRESIGN_SECONDS", "3600")
    )
    replica_primary_overlap_seconds: float = float(
        os.environ.get("REPLICA_PRIMARY_OVERLAP_SECONDS", "0.3")
    )
    replica_analysis_api_key: str = os.environ.get("SILICONFLOW_API_KEY", "")
    replica_analysis_api_url: str = os.environ.get(
        "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/chat/completions"
    )
    replica_vision_model: str = os.environ.get(
        "SILICONFLOW_VISION_MODEL", "Qwen/Qwen3-Omni-30B-A3B-Instruct"
    )
    replica_text_model: str = os.environ.get(
        "SILICONFLOW_TEXT_MODEL", "Qwen/Qwen3.6-27B"
    )
    media_session_ttl_seconds: int = int(
        os.environ.get("MEDIA_SESSION_TTL_SECONDS", str(10 * 60))
    )
    privacy_cleanup_interval_seconds: int = int(
        os.environ.get("PRIVACY_CLEANUP_INTERVAL_SECONDS", "60")
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
