"""Editable prompt-template loading for replica-analysis model calls."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from backend.app.services.replica_analysis.common import ReplicaAnalysisModelError


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True)
class ReplicaPromptTemplate:
    """Load one named system prompt and its expected JSON response schema."""

    system_prompt: str
    response_schema: dict[str, Any]

    @classmethod
    def load(
        cls,
        prompt_filename: str,
        schema_filename: str,
        directory: Path = DEFAULT_PROMPT_PATH,
    ) -> "ReplicaPromptTemplate":
        try:
            system_prompt = (directory / prompt_filename).read_text(encoding="utf-8").strip()
            response_schema = json.loads(
                (directory / schema_filename).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ReplicaAnalysisModelError("复刻分析提示词文件无法读取") from exc
        if not system_prompt or not isinstance(response_schema, dict):
            raise ReplicaAnalysisModelError("复刻分析提示词文件格式不正确")
        return cls(system_prompt=system_prompt, response_schema=response_schema)
