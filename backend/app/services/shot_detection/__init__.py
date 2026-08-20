"""自动分镜服务目录。

downloader：下载已解析的视频到任务目录。
detector：使用 PySceneDetect 识别镜头边界。
exporter：导出每个镜头的视频片段与关键帧。
store：管理缓存、任务文件与安全素材访问。
service：只负责将以上能力编排为自动分镜流程。
"""

from backend.app.services.shot_detection.config import ShotDetectionConfig
from backend.app.services.shot_detection.errors import (
    ShotDecodeError,
    ShotDetectionError,
    ShotMediaDownloadError,
)
from backend.app.services.shot_detection.service import ShotDetectionService

__all__ = (
    "ShotDecodeError",
    "ShotDetectionConfig",
    "ShotDetectionError",
    "ShotDetectionService",
    "ShotMediaDownloadError",
)
