"""File-backed prompt assets for canvas model operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template


DEFAULT_PROMPT_DIRECTORY = Path(__file__).resolve().parents[3] / "prompts" / "canvas"


class CanvasPromptTemplateError(RuntimeError):
    """A canvas prompt asset cannot be loaded."""


@dataclass(frozen=True)
class CanvasPromptTemplates:
    """Editable canvas prompts, kept outside operational services."""

    replacement_analysis_system: str
    replacement_analysis_user: str
    replacement_analysis_merge_system: str
    replacement_analysis_merge_user: Template
    replacement_video_prompt_system: str
    replacement_video_prompt_user: Template
    shot_replacement_video: Template
    multi_shot_replacement_video: Template

    @classmethod
    def load(cls, directory: Path = DEFAULT_PROMPT_DIRECTORY) -> "CanvasPromptTemplates":
        try:
            templates = {
                "replacement_analysis_system": (
                    directory / "replacement_analysis_system.md"
                ).read_text(encoding="utf-8").strip(),
                "replacement_analysis_user": (
                    directory / "replacement_analysis_user.md"
                ).read_text(encoding="utf-8").strip(),
                "replacement_analysis_merge_system": (
                    directory / "replacement_analysis_merge_system.md"
                ).read_text(encoding="utf-8").strip(),
                "replacement_analysis_merge_user": Template(
                    (directory / "replacement_analysis_merge_user.md").read_text(encoding="utf-8").strip()
                ),
                "replacement_video_prompt_system": (
                    directory / "replacement_video_prompt_system.md"
                ).read_text(encoding="utf-8").strip(),
                "replacement_video_prompt_user": Template(
                    (directory / "replacement_video_prompt_user.md").read_text(encoding="utf-8").strip()
                ),
                "shot_replacement_video": Template(
                    (directory / "shot_replacement_video.md").read_text(encoding="utf-8").strip()
                ),
                "multi_shot_replacement_video": Template(
                    (directory / "multi_shot_replacement_video.md").read_text(encoding="utf-8").strip()
                ),
            }
        except OSError as exc:
            raise CanvasPromptTemplateError("画布对象识别提示词文件无法读取") from exc
        if not all(templates.values()):
            raise CanvasPromptTemplateError("画布对象识别提示词模板不能为空")
        return cls(**templates)

    def render_replacement_analysis_merge(self, observations_json: str) -> str:
        try:
            return self.replacement_analysis_merge_user.substitute(
                observations_json=observations_json,
            )
        except (KeyError, ValueError) as exc:
            raise CanvasPromptTemplateError("主体跨片段归并提示词模板参数不完整") from exc

    def render_replacement_video_prompt(
        self,
        *,
        shot_context_json: str,
        subjects_json: str,
    ) -> str:
        try:
            return self.replacement_video_prompt_user.substitute(
                shot_context_json=shot_context_json,
                subjects_json=subjects_json,
            )
        except (KeyError, ValueError) as exc:
            raise CanvasPromptTemplateError("逐镜头多模态提示词模板参数不完整") from exc

    def render_shot_replacement_video(
        self,
        *,
        source_object_name: str,
        source_object_description: str,
        target_description: str,
        target_image_references: str,
        shot_action: str,
    ) -> str:
        try:
            return self.shot_replacement_video.substitute(
                source_object_name=source_object_name,
                source_object_description=source_object_description or "源视频中的该对象",
                target_description=target_description or "以目标参考图片展示的外观、颜色、材质与结构为准",
                target_image_references=target_image_references,
                shot_action=shot_action,
            )
        except (KeyError, ValueError) as exc:
            raise CanvasPromptTemplateError("逐镜头替换提示词模板参数不完整") from exc

    def render_multi_shot_replacement_video(self, replacement_items: str) -> str:
        try:
            return self.multi_shot_replacement_video.substitute(
                replacement_items=replacement_items,
            )
        except (KeyError, ValueError) as exc:
            raise CanvasPromptTemplateError("多主体逐镜头替换提示词模板参数不完整") from exc
