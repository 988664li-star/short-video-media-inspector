"""Shared validation and JSON persistence for replica-analysis services."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


ANALYSIS_ID_PATTERN = re.compile(r"[a-f0-9]{64}")


class ReplicaAnalysisError(RuntimeError):
    """Base error returned by the post-shot replica-analysis APIs."""


class ReplicaAnalysisNotReadyError(ReplicaAnalysisError):
    """A required result from an earlier stage is absent."""


class ReplicaAnalysisModelError(ReplicaAnalysisError):
    """A visual-model request cannot be completed."""


def job_path(data_path: Path, analysis_id: str) -> Path:
    if not ANALYSIS_ID_PATTERN.fullmatch(analysis_id):
        raise ReplicaAnalysisNotReadyError("分镜任务标识无效")
    root = data_path.resolve()
    target = (root / analysis_id).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ReplicaAnalysisNotReadyError("分镜任务路径无效") from exc
    if not (target / "scenes.json").is_file():
        raise ReplicaAnalysisNotReadyError("请先完成自动分镜")
    return target


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(".partial")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)
