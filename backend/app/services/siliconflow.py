"""SiliconFlow JSON chat client shared by replica-analysis services."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from backend.app.core.config import Settings


class SiliconFlowError(RuntimeError):
    """Base error for the external visual-model connector."""


class SiliconFlowConfigurationError(SiliconFlowError):
    """The server is missing the API key required for model calls."""


class SiliconFlowRequestError(SiliconFlowError):
    """The external visual model could not return a usable response."""


@dataclass(frozen=True)
class SiliconFlowConfig:
    api_key: str
    api_url: str
    model: str


class SiliconFlowClient:
    """Make one authenticated JSON chat-completion request at a time."""

    def __init__(self, config: SiliconFlowConfig) -> None:
        self.config = config

    @classmethod
    def from_settings(cls, settings: Settings) -> "SiliconFlowClient":
        return cls(
            SiliconFlowConfig(
                api_key=settings.replica_analysis_api_key,
                api_url=settings.replica_analysis_api_url,
                model=settings.replica_analysis_model,
            )
        )

    async def complete_json(
        self,
        *,
        system_prompt: str,
        content: str | list[dict[str, Any]],
        max_tokens: int,
        timeout_seconds: float,
        temperature: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.config.api_key:
            raise SiliconFlowConfigurationError(
                "服务端未设置 SILICONFLOW_API_KEY，无法生成视觉分析"
            )

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "enable_thinking": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        timeout = httpx.Timeout(connect=20, read=timeout_seconds, write=30, pool=20)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.config.api_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SiliconFlowRequestError(f"视觉模型请求失败：{exc}") from exc

        try:
            message = data["choices"][0]["message"]
            raw_content = str(message["content"]).strip()
            result = json.loads(
                raw_content.removeprefix("```json").removesuffix("```").strip()
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise SiliconFlowRequestError("视觉模型没有返回有效的 JSON 结果") from exc
        if not isinstance(result, dict):
            raise SiliconFlowRequestError("视觉模型返回的数据格式不正确")
        usage = data.get("usage", {})
        return result, usage if isinstance(usage, dict) else {}
