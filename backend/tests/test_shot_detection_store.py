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
