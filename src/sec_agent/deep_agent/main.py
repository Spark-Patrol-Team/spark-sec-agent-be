# -*- coding: utf-8 -*-
"""深度调查 Agent 命令行入口。

用法（在项目根目录，需 src 在导入路径上）：
  PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json
  PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

  -o 指定的文件名会自动插入微秒级时间戳（report.json -> report_20260825_160543_123456.json），
  每次运行生成独立文件，重复运行不会互相覆盖。

依赖环境变量（可选，未设置时走 Mock + 需另配 LLM）：
  LLM_BASE_URL     LLM 接口地址（OpenAI 兼容），如 https://api.deepseek.com
  LLM_API_KEY      LLM 密钥
  LLM_MODEL        模型名，如 deepseek-chat
  TOOL_MODE        mock / mcp / auto（默认 auto）
  MCP_URLS         深信服 MCP 地址（JSON）；未设时读 sec_agent/deep_agent/mcp_servers.local.json
  MCP_API_KEY      深信服 MCP 服务 apikey（漏洞信息查询等需要，可选）
  MCP_VERIFY_SSL   是否校验 MCP HTTPS 证书（自签证书默认 0 关闭，设 1 开启）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import load_config
from .llm import LLMClient
from .models import SecurityEventInput
from .agent import DeepInvestigationAgent
from .tools.base import ToolRegistry
from .tools.mock import build_mock_tools
from .tools.knowledge import build_knowledge_tools
from .tools.mcp_client import build_mcp_tools
from sec_agent.services.gatekeeper import WebShellGatekeeper


def normalize_event_payload(payload: object) -> dict:
    """兼容正式case1-6扁平结构与case7-10的input_event包裹结构。"""
    if not isinstance(payload, dict):
        raise ValueError("事件输入必须是JSON对象")
    event_payload = payload.get("input_event", payload)
    if not isinstance(event_payload, dict):
        raise ValueError("input_event必须是JSON对象")
    return event_payload


def build_tools(config, *, gate_decision: str | None = None) -> ToolRegistry:
    registry = ToolRegistry()

    # Mock 工具兜底（保证闭环可运行）
    if config.tools.mode in ("mock", "auto"):
        for t in build_mock_tools():
            registry.register(t)

    # 知识包检索工具（knowledge.query）：本地资源，所有工具模式下都注册
    # 知识包检索工具：
    # guarded = 注册知识工具；
    # off = 完全不注册知识工具。
    if config.tools.knowledge_mode == "guarded" and gate_decision in {
        "in_scope",
        "weak_signal",
    }:
        for t in build_knowledge_tools(gate_decision=gate_decision):
            registry.register(t)

    # 真实 MCP 工具
    if config.tools.mode in ("mcp", "auto"):
        try:
            for t in build_mcp_tools(config.tools, on_error=lambda m: print(m, file=sys.stderr)):
                registry.register(t)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] MCP 工具接入失败：{e}", file=sys.stderr)

    return registry


def timestamped_output_path(path: str | Path) -> Path:
    """在输出文件名中插入微秒级时间戳，避免重复运行互相覆盖。

    report.json -> report_20260825_160543_123456.json
    reports/foo.json -> reports/foo_20260825_160543_123456.json

    微秒级时间戳已能避免绝大多数同秒重名；若目标文件已存在（极少见的同微秒内
    两次调用或残留文件），自动追加 _1/_2 … 唯一序号，确保绝不重名覆盖。
    """
    p = Path(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    candidate = p.with_name(f"{p.stem}_{stamp}{p.suffix}")
    seq = 1
    while candidate.exists():
        candidate = p.with_name(f"{p.stem}_{stamp}_{seq}{p.suffix}")
        seq += 1
    return candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="深度调查 Agent")
    parser.add_argument("--event", required=True, help="事件输入 JSON 文件路径")
    parser.add_argument("--output", "-o", help="报告输出 JSON 文件路径（自动在文件名中插入时间戳，默认打印到 stdout）")
    parser.add_argument("--list-tools", action="store_true", help="仅列出当前可用工具后退出")
    args = parser.parse_args(argv)

    config = load_config()

    with open(args.event, "r", encoding="utf-8") as f:
        event = SecurityEventInput.from_dict(normalize_event_payload(json.load(f)))

    gate_decision: str | None = None
    if config.tools.knowledge_mode == "guarded":
        try:
            gate_decision = WebShellGatekeeper().audit(event).gate_decision.value
        except Exception as exc:  # noqa: BLE001 - 门禁异常时禁用知识，不得 fail-open
            print(
                f"[warn] 知识门禁审计失败，已禁用知识工具: {type(exc).__name__}",
                file=sys.stderr,
            )
    tools = build_tools(config, gate_decision=gate_decision)

    if args.list_tools:
        print("可用工具（真实名 -> LLM 内部别名）：")
        for n in tools.names():
            alias = tools.alias_of(n)
            print(f" - {n}  ->  {alias}" if alias != n else f" - {n}")
        return 0

    llm = LLMClient(config.llm)
    if not llm.available:
        print("错误：LLM 未配置。请设置环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。", file=sys.stderr)
        return 1

    agent = DeepInvestigationAgent(config, llm, tools)
    report = agent.investigate(event)
    output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)

    if args.output:
        out_path = timestamped_output_path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"报告已写入：{out_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
