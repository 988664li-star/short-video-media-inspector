"""File-backed Seedance prompt templates with explicit business parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


DEFAULT_TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[3] / "prompts" / "seedance"


class SeedancePromptTemplateError(RuntimeError):
    """A required editable Seedance prompt template is missing or invalid."""


@dataclass(frozen=True)
class SeedancePromptTemplates:
    """Render the fixed model rules from files and inject only named parameters."""

    video_edit: Template
    segment_video: Template
    anchor_edit: Template

    @classmethod
    def load(
        cls, directory: Path = DEFAULT_TEMPLATE_DIRECTORY
    ) -> "SeedancePromptTemplates":
        try:
            templates = {
                name: Template((directory / filename).read_text(encoding="utf-8").strip())
                for name, filename in {
                    "video_edit": "video_edit.md",
                    "segment_video": "segment_video.md",
                    "anchor_edit": "anchor_edit.md",
                }.items()
            }
        except OSError as exc:
            raise SeedancePromptTemplateError("Seedance 提示词模板文件无法读取") from exc
        if not all(template.template for template in templates.values()):
            raise SeedancePromptTemplateError("Seedance 提示词模板不能为空")
        return cls(**templates)

    def render_video_edit(
        self, products: list[dict[str, Any]], extra_instruction: str
    ) -> str:
        return self._render(
            self.video_edit,
            product_definitions=self._video_product_definitions(products),
            replacement_actions=self._replacement_actions(products),
            additional_instruction=(extra_instruction.strip() or "无额外补充要求。"),
        )

    def render_segment_video(self, base_instruction: str) -> str:
        return self._render(
            self.segment_video,
            base_instruction=base_instruction,
        )

    def render_anchor_edit(self, segment: dict[str, Any], products: list[dict[str, Any]]) -> str:
        return self._render(
            self.anchor_edit,
            segment_id=f"{int(segment['segment_id']):02d}",
            product_definitions=self._anchor_product_definitions(products),
            replacement_actions=self._replacement_actions(products),
        )

    @staticmethod
    def _render(template: Template, **parameters: str) -> str:
        try:
            return template.substitute(parameters)
        except (KeyError, ValueError) as exc:
            raise SeedancePromptTemplateError("Seedance 提示词模板参数不完整") from exc

    @staticmethod
    def _replacement_actions(products: list[dict[str, Any]]) -> str:
        return "；".join(
            f"将“{product['source_description']}”替换为产品{index}"
            for index, product in enumerate(products, start=1)
        )

    @staticmethod
    def _video_product_definitions(products: list[dict[str, Any]]) -> str:
        definitions: list[str] = []
        image_index = 3
        for ordinal, product in enumerate(products, start=1):
            references = "、".join(
                f"@图片{index}"
                for index in range(image_index, image_index + len(product["file_ids"]))
            )
            definitions.append(
                f"- 产品{ordinal}：{references} 展示的目标产品：{product['target_description']}。"
                "该产品必须始终与这些参考图为同一款实体，不得用源产品的外观补全。"
            )
            image_index += len(product["file_ids"])
        return "\n".join(definitions)

    @staticmethod
    def _anchor_product_definitions(products: list[dict[str, Any]]) -> str:
        definitions: list[str] = []
        image_index = 2
        for ordinal, product in enumerate(products, start=1):
            references = "、".join(
                f"图{index}"
                for index in range(image_index, image_index + len(product["file_ids"]))
            )
            definitions.append(
                f"- {references} 展示同一目标产品，定义为产品{ordinal}：{product['target_description']}。"
                "产品外观只以这些参考图为准，不得从图1的源产品继承颜色、结构或装饰。"
            )
            image_index += len(product["file_ids"])
        return "\n".join(definitions)
