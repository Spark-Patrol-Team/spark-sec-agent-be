# -*- coding: utf-8 -*-
"""深度调查 Agent 命令行入口。

用法：
  python -m deep_agent.main --event test/sample_event.json
  python -m deep_agent.main --event test/sample_event.json --output report.json

依赖环境变量（可选，未设置时走 Mock + 需另配 LLM）：
  LLM_BASE_URL   LLM 接口地址（OpenAI 兼容），如 https://api.deepseek.com
  LLM_API_KEY    LLM 密钥
  LLM_MODEL      模型名，如 deepseek-chat
  TOOL_MODE      mock / mcp / auto（默认 auto）
  MCP_API_KEY    深信服 MCP 服务 apikey（漏洞信息查询等需要）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .llm import LLMClient
from .models import SecurityEventInput
from .agent import DeepInvestigationAgent
from .tools.base import ToolRegistry
from .tools.mock import build_mock_tools
from .tools.mcp_client import build_mcp_tools


def build_tools(config) -> ToolRegistry:
    registry = ToolRegistry()

    # Mock 工具兜底（保证闭环可运行）
    if config.tools.mode in ("mock", "auto"):
        for t in build_mock_tools():
            registry.register(t)

    # 真实 MCP 工具
    if config.tools.mode in ("mcp", "auto"):
        try:
            for t in build_mcp_tools(config.tools, on_error=lambda m: print(m, file=sys.stderr)):
                registry.register(t)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] MCP 工具接入失败：{e}", file=sys.stderr)

    return registry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="深度调查 Agent")
    parser.add_argument("--event", required=True, help="事件输入 JSON 文件路径")
    parser.add_argument("--output", "-o", help="报告输出 JSON 文件路径（默认打印到 stdout）")
    parser.add_argument("--list-tools", action="store_true", help="仅列出当前可用工具后退出")
    args = parser.parse_args(argv)

    config = load_config()
    tools = build_tools(config)

    if args.list_tools:
        print("可用工具：")
        for n in tools.names():
            print(" -", n)
        return 0

    llm = LLMClient(config.llm)
    if not llm.available:
        print("错误：LLM 未配置。请设置环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。", file=sys.stderr)
        return 1

    with open(args.event, "r", encoding="utf-8") as f:
        event = SecurityEventInput.from_dict(json.load(f))

    agent = DeepInvestigationAgent(config, llm, tools)
    report = agent.investigate(event)
    output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"报告已写入：{args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
