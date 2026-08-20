"""媒体转写服务目录。

downloader：下载待转写媒体。
recognizer：加载并运行本地 faster-whisper 识别模型。
punctuation：使用 FunASR 恢复中文标点。
cache：管理临时转写结果与隐私清理。
service：只负责串联下载、识别、标点和缓存流程。
"""

from backend.app.services.transcription.config import TranscriptionConfig
from backend.app.services.transcription.errors import (
    MediaDownloadError,
    ModelUnavailableError,
    PunctuationModelUnavailableError,
    TranscriptionError,
    VocalSeparationError,
)
from backend.app.services.transcription.service import TranscriptionService

__all__ = (
    "MediaDownloadError",
    "ModelUnavailableError",
    "PunctuationModelUnavailableError",
    "TranscriptionConfig",
    "TranscriptionError",
    "TranscriptionService",
    "VocalSeparationError",
)
