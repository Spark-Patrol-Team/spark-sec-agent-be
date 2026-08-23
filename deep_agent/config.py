# -*- coding: utf-8 -*-
"""深度调查 Agent 配置。

统一通过环境变量覆盖，也可直接改默认值。敏感凭据（api key 等）只从环境变量读取，不写死在代码里。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """驱动 Agent 推理的 LLM（OpenAI 兼容接口）。"""
    base_url: str = os.getenv("LLM_BASE_URL", "")    # 如 https://api.deepseek.com
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    temperature: float = 0.0
    timeout: int = 90


@dataclass
class ToolConfig:
    """工具模式：mock / mcp / auto（auto = Mock 兜底 + 连上的真实 MCP 并存）。"""
    mode: str = os.getenv("TOOL_MODE", "auto")
    # 深信服 MCP 地址；内网服务地址已脱敏为占位符，部署到平台内网时替换为真实地址
    mcp_urls: dict = field(default_factory=lambda: {
        "漏洞信息查询": "http://mcp.sec.sangfor.com.cn:31443/mcp",
        "检测大模型": "http://<internal-mcp-host>:8080/mcp/detect_model",
        "网络安全数据查询": "http://<internal-mcp-host>:8080/mcp/network_security",
        "运营大模型": "http://<internal-mcp-host>:8080/mcp/operation_model",
        "自由数据查询": "http://<internal-mcp-host>:8080/mcp/free_query",
    })
    mcp_api_key: str = os.getenv("MCP_API_KEY", "")   # 漏洞信息查询等需要
    mcp_timeout: int = 20


@dataclass
class AgentConfig:
    """深度调查行为参数。"""
    max_steps: int = 5          # 停止条件二：调查步数 >= 5
    max_tool_calls: int = 8     # 单次调查最多工具调用次数（硬上限，防死循环）


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)


def load_config() -> Config:
    return Config()
