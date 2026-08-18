from backend.app.core.config import settings
from backend.app.services.media import MediaRegistry
from backend.app.services.replica_analysis import (
    ReplicaPlaybookService,
    ScenePackageService,
    SceneVisualAnalysisService,
)
from backend.app.services.session import LoginCookieStore
from backend.app.services.shot_detection import ShotDetectionService
from backend.app.services.siliconflow import SiliconFlowClient
from backend.app.services.transcription import TranscriptionService


cookie_store = LoginCookieStore()
media_registry = MediaRegistry()
transcription_service = TranscriptionService.from_settings(settings)
shot_detection_service = ShotDetectionService.from_settings(settings)
siliconflow_client = SiliconFlowClient.from_settings(settings)
scene_package_service = ScenePackageService.from_settings(settings, transcription_service)
scene_visual_analysis_service = SceneVisualAnalysisService(
    settings.shot_detection_data_path, siliconflow_client
)
replica_playbook_service = ReplicaPlaybookService(
    settings.shot_detection_data_path, siliconflow_client
)


def get_cookie_store() -> LoginCookieStore:
    return cookie_store


def get_media_registry() -> MediaRegistry:
    return media_registry


def get_transcription_service() -> TranscriptionService:
    return transcription_service


def get_shot_detection_service() -> ShotDetectionService:
    return shot_detection_service


def get_scene_package_service() -> ScenePackageService:
    return scene_package_service


def get_scene_visual_analysis_service() -> SceneVisualAnalysisService:
    return scene_visual_analysis_service


def get_replica_playbook_service() -> ReplicaPlaybookService:
    return replica_playbook_service
