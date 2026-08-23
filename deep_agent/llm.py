# -*- coding: utf-8 -*-
"""LLM 客户端：OpenAI 兼容接口封装（DeepSeek / 通义 / GLM / 深信服等均兼容）。"""
from __future__ import annotations

from typing import Any, Optional

from .config import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        if config.base_url and config.api_key:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """返回一条 assistant message dict，可直接 append 到 messages 继续多轮。

        返回结构：
            {
              "role": "assistant",
              "content": "...",          # 纯文本回答（未请求工具调用时）
              "tool_calls": [             # 请求工具调用时
                {"id": "...", "type": "function",
                 "function": {"name": "...", "arguments": "{...}"}}
              ]
            }
        """
        if not self.available:
            raise RuntimeError(
                "LLM 未配置，请设置环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"
            )
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        if tools:
            kwargs["tools"] = tools

        resp = self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        tool_calls = []
        for tc in (msg.tool_calls or []):
            tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            })

        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls,
        }
