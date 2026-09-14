# -*- coding: utf-8 -*-
"""out_of_scope 报告措辞约束与 PR58 证据隔离的组合回归。"""
from __future__ import annotations

import json

import pytest
import sec_agent.deep_agent.agent as agent_module

from sec_agent.deep_agent.agent import (
    DeepInvestigationAgent,
    _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER,
    _OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER,
    _OUT_OF_SCOPE_REPORT_CONSTRAINT,
    sanitize_out_of_scope_report,
)
from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.deep_agent.tools.base import Tool, ToolRegistry, ToolResult


@pytest.mark.parametrize(
    "attack_chain",
    [
        "攻击者植入后门并建立持久化，随后投递最终载荷",
        "The actor established persistence and delivered a final payload",
        "A backdoor dropped a WebShell payload",
    ],
)
def test_sanitize_rewrites_attack_chain_variants(attack_chain: str) -> None:
    cleaned = sanitize_out_of_scope_report(
        {"attack_chain": attack_chain, "disposal_suggestions": ["保留日志"]}
    )

    assert cleaned["attack_chain"] == _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER


def test_sanitize_filters_scope_specific_disposal() -> None:
    source = {
        "attack_chain": "无法构建可信攻击链",
        "disposal_suggestions": [
            "排查 WebShell 文件",
            "Kill the BACKDOOR and remove the trojan",
            "保留日志并转交身份安全场景",
        ],
    }

    cleaned = sanitize_out_of_scope_report(source)

    assert cleaned["disposal_suggestions"] == ["保留日志并转交身份安全场景"]
    assert source["disposal_suggestions"][0] == "排查 WebShell 文件"


def test_sanitize_adds_neutral_disposal_when_every_suggestion_is_removed() -> None:
    cleaned = sanitize_out_of_scope_report(
        {
            "attack_chain": "无法构建可信攻击链",
            "disposal_suggestions": ["查杀后门", "清除 WebShell"],
        }
    )

    assert cleaned["disposal_suggestions"] == [_OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER]


def test_prompt_constraint_is_only_added_for_out_of_scope() -> None:
    agent = DeepInvestigationAgent.__new__(DeepInvestigationAgent)
    event = SecurityEventInput(event_id="E-prompt", event_type="other")

    scoped = agent._build_messages(event, gate_decision="out_of_scope")
    weak = agent._build_messages(event, gate_decision="weak_signal")
    missing = agent._build_messages(event)

    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT in scoped[0]["content"]
    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT not in weak[0]["content"]
    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT not in missing[0]["content"]


class _EventTool(Tool):
    name = "query_alerts"
    description = "test event observation"
    parameters = {"type": "object", "properties": {}}

    def call(self, params):
        return ToolResult(status="success", summary="事件观测：SSH 连续登录失败")


class _HostileLLM:
    available = True

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "event-call",
                        "function": {"name": "query_alerts", "arguments": "{}"},
                    }
                ],
            }
        return {
            "content": json.dumps(
                {
                    "conclusion": "证据不足，需转交身份安全场景",
                    "risk_level": "HIGH",
                    "attack_type": "other",
                    "key_evidence": ["LLM伪造的知识结论"],
                    "evidence_source": ["来源工具: knowledge_query"],
                    "investigation_steps": [],
                    "attack_chain": "攻击者建立 persistence 并投递 final payload",
                    "confidence": 0.4,
                    "disposal_suggestions": ["排查 WebShell 文件", "保留认证日志"],
                    "need_manual_takeover": True,
                    "manual_takeover_reason": "需转交其他场景",
                    "unresolved_issues": ["身份攻击链待确认"],
                    "affected_objects": [],
                },
                ensure_ascii=False,
            ),
            "tool_calls": [],
        }


def test_hostile_normal_report_is_sanitized_without_breaking_evidence_isolation() -> None:
    registry = ToolRegistry()
    registry.register(_EventTool())
    config = type("Config", (), {"agent": type("Agent", (), {"max_tool_calls": 2})()})()
    report = DeepInvestigationAgent(config, _HostileLLM(), registry).investigate(
        SecurityEventInput(
            event_id="E-hostile",
            event_type="other",
            evidence=["evt-ref: SSH 登录失败"],
        ),
        gate_decision="out_of_scope",
    )

    assert report.attack_chain == _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER
    assert report.disposal_suggestions == ["保留认证日志"]
    assert report.key_evidence == ["evt-ref: SSH 登录失败", "事件观测：SSH 连续登录失败"]
    assert report.evidence_source == ["上游风险研判", "来源工具: query_alerts"]


def test_out_of_scope_fallback_uses_same_sanitizer(monkeypatch) -> None:
    called = []
    original = agent_module.sanitize_out_of_scope_report

    def tracking_sanitizer(data):
        called.append(True)
        return original(data)

    monkeypatch.setattr(agent_module, "sanitize_out_of_scope_report", tracking_sanitizer)
    report = DeepInvestigationAgent._fallback_report(
        SecurityEventInput(event_id="E-fallback", event_type="other"),
        [],
        reason="达到上限",
        gate_decision="out_of_scope",
    )

    assert called == [True]
    assert report.attack_chain == "未知"
    assert report.disposal_suggestions == ["建议人工介入进一步调查"]
