from backend.app.core.config import settings
from backend.app.services.media import MediaRegistry
from backend.app.services.replica_analysis import (
    ReplicaPlaybookService,
    ScenePackageService,
)
from backend.app.services.session import LoginCookieStore
from backend.app.services.shot_detection import ShotDetectionService
from backend.app.services.siliconflow import SiliconFlowClient
from backend.app.services.seedance import SeedanceWorkspaceService
from backend.app.services.seedance.object_storage import SeedanceObjectStorage
from backend.app.services.storyboard import StoryboardChunkService, StoryboardScriptService
from backend.app.services.transcription import TranscriptionService


cookie_store = LoginCookieStore()
media_registry = MediaRegistry()
transcription_service = TranscriptionService.from_settings(settings)
shot_detection_service = ShotDetectionService.from_settings(settings)
siliconflow_vision_client = SiliconFlowClient.from_settings(
    settings, model=settings.replica_vision_model
)
siliconflow_text_client = SiliconFlowClient.from_settings(
    settings, model=settings.replica_text_model
)
scene_package_service = ScenePackageService.from_settings(settings, transcription_service)
replica_playbook_service = ReplicaPlaybookService(
    settings.shot_detection_data_path, siliconflow_text_client
)
storyboard_chunk_service = StoryboardChunkService.from_settings(settings)
storyboard_script_service = StoryboardScriptService(
    settings.shot_detection_data_path, siliconflow_vision_client
)
seedance_workspace_service = SeedanceWorkspaceService(
    settings.replica_workspace_db_path,
    settings.seedance_api_key,
    settings.seedance_api_url,
    settings.ark_files_api_url,
    settings.ark_file_max_bytes,
    SeedanceObjectStorage(
        settings.seedance_object_storage_endpoint,
        settings.seedance_object_storage_access_key,
        settings.seedance_object_storage_secret_key,
        settings.seedance_object_storage_bucket,
        settings.seedance_object_storage_presign_seconds,
    ),
    settings.shot_detection_data_path,
    settings.shot_detection_ffmpeg_binary,
    settings.seedream_api_url,
    settings.seedream_model,
    settings.gpt_image_api_key,
    settings.gpt_image_edits_url,
    settings.gpt_image_model,
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


def get_replica_playbook_service() -> ReplicaPlaybookService:
    return replica_playbook_service


def get_storyboard_chunk_service() -> StoryboardChunkService:
    return storyboard_chunk_service


def get_storyboard_script_service() -> StoryboardScriptService:
    return storyboard_script_service


def get_seedance_workspace_service() -> SeedanceWorkspaceService:
    return seedance_workspace_service
