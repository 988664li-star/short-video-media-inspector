"""SiliconFlow JSON chat client shared by replica-analysis services."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

import httpx

from backend.app.core.config import Settings


logger = logging.getLogger(__name__)


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
    def from_settings(
        cls,
        settings: Settings,
        *,
        model: str | None = None,
    ) -> "SiliconFlowClient":
        return cls(
            SiliconFlowConfig(
                api_key=settings.replica_analysis_api_key,
                api_url=settings.replica_analysis_api_url,
                model=model or settings.replica_analysis_model,
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
        log_context: str = "",
        enable_thinking: bool | None = None,
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
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if enable_thinking is not None:
            payload["enable_thinking"] = enable_thinking
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
        except httpx.HTTPStatusError as exc:
            response = exc.response
            trace_id = response.headers.get("x-siliconcloud-trace-id", "")
            detail = response.text.strip().replace("\n", " ")[:800]
            suffix = f"；trace_id={trace_id}" if trace_id else ""
            raise SiliconFlowRequestError(
                f"视觉模型请求失败（HTTP {response.status_code}）：{detail}{suffix}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SiliconFlowRequestError(f"视觉模型请求失败：{exc}") from exc

        logger.info(
            "SiliconFlow 完整 API 响应%s [model=%s]: %s",
            f" [{log_context}]" if log_context else "",
            self.config.model,
            json.dumps(data, ensure_ascii=False),
        )
        try:
            message = data["choices"][0]["message"]
            raw_value = message.get("content")
            raw_content = raw_value.strip() if isinstance(raw_value, str) else ""
            if not raw_content:
                finish_reason = data["choices"][0].get("finish_reason", "unknown")
                raise SiliconFlowRequestError(
                    f"模型返回空内容（finish_reason={finish_reason}）；请查看完整 API 响应日志"
                )
            logger.info(
                "SiliconFlow 原始模型返回%s [model=%s]: %s",
                f" [{log_context}]" if log_context else "",
                self.config.model,
                raw_content,
            )
            result = json.loads(
                raw_content.removeprefix("```json").removesuffix("```").strip()
            )
        except SiliconFlowRequestError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise SiliconFlowRequestError("视觉模型没有返回有效的 JSON 结果") from exc
        if not isinstance(result, dict):
            raise SiliconFlowRequestError("视觉模型返回的数据格式不正确")
        usage = data.get("usage", {})
        return result, usage if isinstance(usage, dict) else {}
