# -*- coding: utf-8 -*-
"""工具抽象基类、统一结果与注册表。

真实 MCP 工具与 Mock 工具遵循同一契约（对齐《统一接口与数据流》8 节），
使 Agent 的调查循环不依赖具体工具实现。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# 内部别名（LLM 函数名兼容层）
#
# OpenAI 兼容接口强制函数名匹配 ^[a-zA-Z0-9_-]+$，而深信服 MCP 工具的真实
# 函数名含中文（如 cybersec_攻击状态检测），直接作为 schema 发给 LLM 会被
# 400 拒绝。因此在发送 schema 前把真实名翻译为 ASCII 内部别名；LLM 返回别名
# 后由 ToolRegistry.resolve() 还原真实名再执行真实 MCP 调用。
# --------------------------------------------------------------------------- #
ALIAS_MAP: dict[str, str] = {
    # 检测大模型
    "cybersec_攻击状态检测": "cybersec_attack_status_detect",
    "cybersec_攻击类型检测": "cybersec_attack_type_detect",
    # 网络安全数据查询
    "incidents_安全事件相关的查询和统计": "incidents_query_statistics",
    "alerts_安全告警相关的查询和统计": "alerts_query_statistics",
    "vul_漏洞相关的查询和统计": "vul_query_statistics",
    "vul_弱密码相关的查询和统计": "vul_weak_password_query",
    "vul_资产关联漏洞数据查询": "vul_asset_related_query",
    "assets_资产相关的查询和统计": "assets_query_statistics",
    # 运营大模型
    "secgpt_告警事件解读研判": "secgpt_alert_interpretation",
    "secgpt_威胁实体的调查分析": "secgpt_threat_entity_analysis",
    # 自由数据查询
    "dbproxy_事件数据查询工具": "dbproxy_event_query",
    "dbproxy_告警数据查询工具": "dbproxy_alert_query",
    "dbproxy_脆弱性数据查询工具": "dbproxy_vulnerability_query",
    "dbproxy_资产数据查询工具": "dbproxy_asset_query",
    "dbproxy_威胁实体数据查询工具": "dbproxy_threat_entity_query",
}

# 真实函数名里非法字符（非字母数字下划线中划线）
_FUNCTION_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _auto_alias(name: str, taken: set[str]) -> str:
    """为未收录在 ALIAS_MAP 中的工具自动生成 ASCII 内部别名（确定性、去重）。"""
    base = _FUNCTION_NAME_RE.sub("", name).strip("_-") or "tool"
    candidate = base
    i = 1
    while candidate in taken:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


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

    def to_openai_schema(self, name_override: Optional[str] = None) -> dict:
        """输出 OpenAI function schema；name_override 用于发送给 LLM 的 ASCII 内部别名。"""
        return {
            "type": "function",
            "function": {
                "name": name_override or self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表：注册、查找、统一调用（带异常兜底）。

    注册时为每个工具计算内部别名（含中文名的 MCP 工具映射为 ASCII），
    schemas() 发送别名给 LLM，call()/resolve() 把别名还原回真实名执行。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._aliases: dict[str, str] = {}    # 真实名 -> 内部别名
        self._real_names: dict[str, str] = {}  # 内部别名 -> 真实名

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        alias = ALIAS_MAP.get(tool.name) or _auto_alias(tool.name, set(self._aliases.values()))
        self._aliases[tool.name] = alias
        self._real_names[alias] = tool.name
        return tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        """真实工具名（MCP 层原名，仅用于展示/审计）。"""
        return list(self._tools.keys())

    def aliases(self) -> list[str]:
        """内部别名（LLM 层使用的函数名），与 names() 顺序一致。"""
        return [self._aliases[n] for n in self._tools]

    def alias_of(self, name: str) -> str:
        """真实名 -> 内部别名；别名与真实名相同（ASCII 工具）时原样返回。"""
        return self._aliases.get(name, name)

    def resolve(self, name: str) -> str:
        """把 LLM 返回的内部别名解析回真实工具名；本身即真实名时原样返回。"""
        return self._real_names.get(name, name)

    def schemas(self) -> list[dict]:
        return [t.to_openai_schema(name_override=self._aliases[t.name]) for t in self._tools.values()]

    def call(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(self.resolve(name))
        if not tool:
            return ToolResult(status="failed", error=f"未知工具: {name}")
        try:
            return tool.call(params)
        except Exception as e:  # noqa: BLE001
            return ToolResult(status="failed", error=f"{type(e).__name__}: {e}")
