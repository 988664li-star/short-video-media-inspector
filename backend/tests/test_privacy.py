import os
from pathlib import Path
import time

from backend.app.services.session import LoginCookieStore, remove_cookie_file
from backend.app.services.transcription import TranscriptionConfig, TranscriptionService


def _service(cache_path: Path, ttl_seconds: int) -> TranscriptionService:
    return TranscriptionService(
        TranscriptionConfig(
            model_size="small",
            language="zh",
            device="cpu",
            compute_type="int8",
            cpu_threads=1,
            max_media_bytes=1,
            model_path=cache_path / "models",
            cache_path=cache_path,
            cache_ttl_seconds=ttl_seconds,
            punctuation_model="ct-punc",
            punctuation_device="cpu",
        )
    )


def test_default_cookie_store_only_uses_memory():
    assert LoginCookieStore().status()["storage"] == "memory"


def test_expired_transcript_cache_is_removed(tmp_path: Path):
    expired = tmp_path / "expired.json"
    recent = tmp_path / "recent.json"
    expired.write_text("{}", encoding="utf-8")
    recent.write_text("{}", encoding="utf-8")
    os.utime(expired, (time.time() - 61, time.time() - 61))

    service = _service(tmp_path, ttl_seconds=60)
    assert service.cleanup_expired_cache() == 1
    assert not expired.exists()
    assert recent.exists()


def test_legacy_cookie_file_is_removed(tmp_path: Path):
    cookie_path = tmp_path / "douyin_cookie.json"
    cookie_path.write_text('{"cookie":"sessionid=secret"}', encoding="utf-8")
    remove_cookie_file(cookie_path)
    assert not cookie_path.exists()
