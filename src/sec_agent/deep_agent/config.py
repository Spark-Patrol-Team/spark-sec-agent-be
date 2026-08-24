# -*- coding: utf-8 -*-
"""深度调查 Agent 配置。

统一通过环境变量覆盖，也可直接改默认值。敏感凭据（api key、内网 MCP 地址）只从
环境变量或本地未入库的配置文件读取，不写死在代码里，避免泄露到 Git 仓库。

LLM API 本地配置文件为 `llm_config.local.json`（与 config.py 同目录，已 gitignore），
由可视化界面 `config_gui.py` 写入/清除，也可手动编辑。解析优先级：环境变量 > 本地文件 > 默认值。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_mcp_urls() -> dict:
    """加载深信服 MCP 服务地址。

    优先级：
      1. 环境变量 MCP_URLS（JSON 字符串，如 {"漏洞信息查询": "https://..."}）
      2. 本地配置文件 mcp_servers.local.json（与 config.py 同目录，已 gitignore，不入库）

    代码里不写死真实地址，避免内网 MCP 地址泄露到 Git 仓库。
    """
    raw = os.getenv("MCP_URLS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    local = Path(__file__).with_name("mcp_servers.local.json")
    if local.exists():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass

    return {}


# --------------------------------------------------------------------------- #
# LLM API 本地配置（含 apikey，不入库）
# --------------------------------------------------------------------------- #
_API_CONFIG_FILE = "llm_config.local.json"


def api_config_path() -> Path:
    """本地 API 配置文件路径（与 config.py 同目录，已 gitignore）。"""
    return Path(__file__).with_name(_API_CONFIG_FILE)


def load_api_config_file() -> dict:
    """读取本地 API 配置文件（仅文件内容，不含环境变量覆盖）。"""
    p = api_config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_api_config(
    base_url: str = "",
    api_key: str = "",
    model: str = "deepseek-chat",
    temperature: float = 0.0,
    timeout: int = 90,
) -> Path:
    """把 LLM API 配置写入本地文件（含 apikey，不入库），返回文件路径。"""
    data = {
        "base_url": str(base_url).strip(),
        "api_key": str(api_key).strip(),
        "model": str(model).strip(),
        "temperature": float(temperature),
        "timeout": int(timeout),
    }
    p = api_config_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def clear_api_config() -> bool:
    """删除本地 API 配置文件。返回是否确有删除。"""
    p = api_config_path()
    if p.exists():
        p.unlink()
        return True
    return False


def _llm_str(env_name: str, file_key: str, default: str):
    """按「环境变量 > 本地文件 > 默认值」解析字符串字段。"""
    def factory() -> str:
        env = os.getenv(env_name, "").strip()
        if env:
            return env
        val = load_api_config_file().get(file_key)
        if val not in (None, ""):
            return str(val)
        return default
    return factory


def _llm_num(env_name: str, file_key: str, default, cast):
    """按「环境变量 > 本地文件 > 默认值」解析数值字段。"""
    def factory():
        env = os.getenv(env_name, "").strip()
        raw = env if env else load_api_config_file().get(file_key)
        if raw in (None, ""):
            return default
        try:
            return cast(raw)
        except (TypeError, ValueError):
            return default
    return factory


@dataclass
class LLMConfig:
    """驱动 Agent 推理的 LLM（OpenAI 兼容接口）。

    解析优先级：环境变量 > 本地文件 llm_config.local.json > 默认值。
    """
    base_url: str = field(default_factory=_llm_str("LLM_BASE_URL", "base_url", ""))
    api_key: str = field(default_factory=_llm_str("LLM_API_KEY", "api_key", ""))
    model: str = field(default_factory=_llm_str("LLM_MODEL", "model", "deepseek-chat"))
    temperature: float = field(default_factory=_llm_num("LLM_TEMPERATURE", "temperature", 0.0, float))
    timeout: int = field(default_factory=_llm_num("LLM_TIMEOUT", "timeout", 90, int))


@dataclass
class ToolConfig:
    """工具模式：mock / mcp / auto（auto = Mock 兜底 + 连上的真实 MCP 并存）。"""
    mode: str = os.getenv("TOOL_MODE", "auto")
    # 深信服 MCP 服务地址：从 MCP_URLS 环境变量或 mcp_servers.local.json 读取（真实地址不入库）
    mcp_urls: dict = field(default_factory=_load_mcp_urls)
    mcp_api_key: str = os.getenv("MCP_API_KEY", "")   # 漏洞信息查询等需要的 apikey（可选）
    mcp_timeout: int = 20
    # 深信服 MCP 走 HTTPS 自签证书/IP 直连，默认关闭证书校验；设 MCP_VERIFY_SSL=1 开启
    mcp_verify_ssl: bool = os.getenv("MCP_VERIFY_SSL", "0") == "1"


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
