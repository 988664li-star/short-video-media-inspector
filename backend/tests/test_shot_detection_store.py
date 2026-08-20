from pathlib import Path

from backend.app.services.shot_detection.store import ShotDetectionStore


def test_cleanup_keeps_active_incomplete_job(tmp_path: Path):
    store = ShotDetectionStore(tmp_path, cache_ttl_seconds=1)
    active_job = tmp_path / "active-job"
    active_job.mkdir()
    (active_job / ".active").touch()

    assert store.cleanup_expired() == 0
    assert active_job.exists()


def test_cleanup_keeps_incomplete_job_without_result(tmp_path: Path):
    store = ShotDetectionStore(tmp_path, cache_ttl_seconds=1)
    incomplete_job = tmp_path / "incomplete-job"
    incomplete_job.mkdir()

    assert store.cleanup_expired() == 0
    assert incomplete_job.exists()


def test_cache_key_uses_stable_aweme_identity_not_expiring_cdn_url(tmp_path: Path):
    store = ShotDetectionStore(tmp_path, cache_ttl_seconds=1)

    first = store.cache_key("1234567890", "https://cdn.example/a?expires=1", 27, 0.5)
    refreshed = store.cache_key("1234567890", "https://cdn.example/b?expires=2", 27, 0.5)

    assert first == refreshed
