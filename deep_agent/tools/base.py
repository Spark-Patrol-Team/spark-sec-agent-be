# -*- coding: utf-8 -*-
"""工具抽象基类、统一结果与注册表。

真实 MCP 工具与 Mock 工具遵循同一契约（对齐《统一接口与数据流》8 节），
使 Agent 的调查循环不依赖具体工具实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """统一工具结果。"""
    status: str = "success"        # success / failed / partial
    summary: str = ""              # 结果摘要（供 LLM 阅读）
    data: Any = None               # 原始结果数据
    error: str = ""                # 错误类型 / 信息
    retryable: bool = False        # 是否可重试
    has_side_effect: bool = False  # 是否产生外部副作用

    def to_str(self) -> str:
        if self.status == "failed":
            return f"[失败] {self.error or self.summary}"
        if self.status == "partial":
            return f"[部分成功] {self.summary}"
        return self.summary


class Tool(ABC):
    """工具抽象基类。"""
    name: str = ""
    description: str = ""
    parameters: dict = {}   # JSON Schema

    @abstractmethod
    def call(self, params: dict) -> ToolResult:
        raise NotImplementedError

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表：注册、查找、统一调用（带异常兜底）。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def call(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(status="failed", error=f"未知工具: {name}")
        try:
            return tool.call(params)
        except Exception as e:  # noqa: BLE001
            return ToolResult(status="failed", error=f"{type(e).__name__}: {e}")
