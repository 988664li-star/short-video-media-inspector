from backend.app.core.config import settings
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore
from backend.app.services.transcription import TranscriptionService


cookie_store = LoginCookieStore(settings.cookie_store_path)
media_registry = MediaRegistry()
transcription_service = TranscriptionService.from_settings(settings)


def get_cookie_store() -> LoginCookieStore:
    return cookie_store


def get_media_registry() -> MediaRegistry:
    return media_registry


def get_transcription_service() -> TranscriptionService:
    return transcription_service
