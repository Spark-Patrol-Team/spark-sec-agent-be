# -*- coding: utf-8 -*-
"""知识门禁（event_context 绑定 + 三档折叠）测试。

覆盖 T0905-04 任务1：
- 6 档 → 3 档折叠（OUT / WEAK / CONFIRMED）；
- knowledge_query 依据注入的 event_context 拒绝域外事件（knowledge_scope_mismatch）；
- Agent 在 investigate 中注入真实事件上下文，覆盖 LLM 自报的 event_context。
"""
from __future__ import annotations

import json
from pathlib import Path

from sec_agent.deep_agent.agent import DeepInvestigationAgent
from sec_agent.deep_agent.config import load_config
from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.deep_agent.tools.base import ToolRegistry
from sec_agent.deep_agent.tools.knowledge import build_knowledge_tools, fold_scope

CASES_DIR = Path(__file__).resolve().parent / "fixtures" / "gatekeeper_cases"


def _load_case(i: int) -> dict:
    with open(CASES_DIR / f"case{i}.json", "r", encoding="utf-8") as f:
        return json.load(f)


class _FakeLLM:
    """最小假 LLM：按预设回复序列返回 chat 结果（不依赖真实 LLM 密钥）。"""
    available = True

    def __init__(self, replies):
        self._replies = list(replies)

    def chat(self, messages, tools=None):
        return self._replies.pop(0)


# --------------------------------------------------------------------------- #
# 三档折叠
# --------------------------------------------------------------------------- #
def test_fold_scope_out():
    assert fold_scope("OUT_OF_SCOPE") == "OUT"


def test_fold_scope_confirmed():
    assert fold_scope("IN_SCOPE_CONFIRMED") == "CONFIRMED"


def test_fold_scope_weak():
    for strength in ("IN_SCOPE_WEAK", "MIXED", "BENIGN_LIKE", "INDETERMINATE"):
        assert fold_scope(strength) == "WEAK", strength


def test_fold_scope_missing_falls_back_confirmed():
    # 未注入门禁上下文 → 向后兼容放行（知识工具单测直接按 keyword 检索）
    assert fold_scope("") == "CONFIRMED"


# --------------------------------------------------------------------------- #
# knowledge_query 依据 event_context 决定是否放行
# --------------------------------------------------------------------------- #
def test_knowledge_query_rejects_out_of_scope():
    tool = build_knowledge_tools()[0]
    result = tool.call({"keyword": "WebShell攻击原理", "event_context": {"overall_strength": "OUT_OF_SCOPE"}})
    assert result.status == "failed"
    assert result.error == "knowledge_scope_mismatch"
    assert result.data is None  # 不返回 WebShell 知识卡片


def test_knowledge_query_weak_marks_hint():
    tool = build_knowledge_tools()[0]
    result = tool.call({"keyword": "WebShell攻击原理", "event_context": {"overall_strength": "IN_SCOPE_WEAK"}})
    assert result.status == "success"
    assert result.data["scope"] == "WEAK"
    assert "弱信号" in result.summary


def test_knowledge_query_confirmed_normal():
    tool = build_knowledge_tools()[0]
    result = tool.call({"keyword": "WebShell攻击原理", "event_context": {"overall_strength": "IN_SCOPE_CONFIRMED"}})
    assert result.status == "success"
    assert result.data["scope"] == "CONFIRMED"
    assert "弱信号" not in result.summary


# --------------------------------------------------------------------------- #
# Agent 侧：绑定真实事件上下文
# --------------------------------------------------------------------------- #
def test_agent_builds_out_of_scope_context_for_case6():
    event = SecurityEventInput.from_dict(_load_case(6)["input_event"])
    ctx = DeepInvestigationAgent._build_event_context(event)
    assert ctx["overall_strength"] == "OUT_OF_SCOPE"


def test_agent_builds_confirmed_context_for_case9():
    event = SecurityEventInput.from_dict(_load_case(9)["input_event"])
    ctx = DeepInvestigationAgent._build_event_context(event)
    assert ctx["overall_strength"] == "IN_SCOPE_CONFIRMED"


def test_agent_injects_real_context_overriding_llm():
    """LLM 恶意自报 event_context=IN_SCOPE_CONFIRMED 也应被真实事件（case6 OOS）覆盖。"""
    event = SecurityEventInput.from_dict(_load_case(6)["input_event"])
    config = load_config()
    tools = ToolRegistry()
    for t in build_knowledge_tools():
        tools.register(t)

    fake = _FakeLLM([
        {
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "function": {
                    "name": "knowledge_query",
                    "arguments": json.dumps({
                        "keyword": "WebShell攻击原理",
                        # LLM 自报：恶意声称事件在 WebShell 域内
                        "event_context": {"overall_strength": "IN_SCOPE_CONFIRMED"},
                    }),
                },
            }],
        },
        {"content": json.dumps({"conclusion": "done"}), "tool_calls": []},
    ])

    agent = DeepInvestigationAgent(config, fake, tools)
    report = agent.investigate(event)

    rec = report.tool_call_records[0]
    assert rec["tool"] == "knowledge_query"
    # 真实事件上下文覆盖 LLM 自报
    assert rec["input"]["event_context"]["overall_strength"] == "OUT_OF_SCOPE"
    # 因此 knowledge_query 被门禁拒绝，不返回 WebShell 知识
    assert rec["status"] == "failed"


# --------------------------------------------------------------------------- #
# 任务4：改写 query 不绕过 + 最终报告不误结论
# --------------------------------------------------------------------------- #
def test_knowledge_query_out_of_scope_rejects_regardless_of_keyword():
    """LLM 改写 query 不能绕过门禁：OUT 场景下任意 keyword 都被拒绝。"""
    tool = build_knowledge_tools()[0]
    for kw in ("WebShell攻击原理", "WebShell处置建议", "证据检查清单", "攻击原理", "无关关键词"):
        result = tool.call({"keyword": kw, "event_context": {"overall_strength": "OUT_OF_SCOPE"}})
        assert result.status == "failed", kw
        assert result.error == "knowledge_scope_mismatch", kw


# 任务4 Layer 2 禁止出现的「无输入支撑攻击确认」关键词
_FALSE_CONFIRM_WORDS = ("WebShell植入", "植入WebShell", "WebShell通信", "持久化", "最终载荷", "清除动作")


def _assert_no_false_webshell_conclusion(report) -> None:
    d = report.to_dict()
    for field in ("conclusion", "attack_chain", "attack_type"):
        text = str(d.get(field) or "")
        for word in _FALSE_CONFIRM_WORDS:
            assert word not in text, f"{field} 含误结论词 {word}: {text}"


def _run_out_of_scope_case(case_no: int):
    event = SecurityEventInput.from_dict(_load_case(case_no)["input_event"])
    config = load_config()
    tools = ToolRegistry()
    for t in build_knowledge_tools():
        tools.register(t)
    fake = _FakeLLM([
        {
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "knowledge_query", "arguments": json.dumps({"keyword": "WebShell攻击原理"})},
            }],
        },
        {"content": json.dumps({"conclusion": "调查完成"}), "tool_calls": []},
    ])
    agent = DeepInvestigationAgent(config, fake, tools)
    return agent.investigate(event)


def test_case6_report_has_no_false_webshell_conclusion():
    report = _run_out_of_scope_case(6)
    rec = report.tool_call_records[0]
    # Layer 1：knowledge_query 被拒，审计记录 knowledge_scope_mismatch
    assert rec["status"] == "failed"
    assert rec["output"] == "[失败] knowledge_scope_mismatch"
    # Layer 2：无成功工具 → 降级为证据不足，无 WebShell 攻击确认
    assert report.need_manual_takeover is True
    assert "证据不足" in report.conclusion
    _assert_no_false_webshell_conclusion(report)


def test_case10_report_has_no_false_webshell_conclusion():
    report = _run_out_of_scope_case(10)
    rec = report.tool_call_records[0]
    assert rec["status"] == "failed"
    assert rec["output"] == "[失败] knowledge_scope_mismatch"
    assert report.need_manual_takeover is True
    assert "证据不足" in report.conclusion
    _assert_no_false_webshell_conclusion(report)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
