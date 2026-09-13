# -*- coding: utf-8 -*-
"""域外事件（out_of_scope）报告措辞约束的确定性测试。

对应评审结论（2026-09-13）：知识门禁本身正确，但 out_of_scope 报告的措辞仍会越界——
attack_chain 不得写「植入/持久化」等 WebShell 攻击链特征，disposal_suggestions
不得写「清除/排查 WebShell」等 WebShell 专属处置。

本文件用「纯函数清洗」和「消息构造」两条路径做确定性检查，不依赖 LLM。
"""
from sec_agent.deep_agent.agent import (
    DeepInvestigationAgent,
    sanitize_out_of_scope_report,
    _OUT_OF_SCOPE_REPORT_CONSTRAINT,
    _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER,
    _OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER,
)
from sec_agent.deep_agent.models import SecurityEventInput


def test_sanitize_rewrites_attack_chain_with_webshell_terms():
    data = {
        "attack_chain": "攻击者在WordPress站点植入内容并创建隐藏管理员账户，从而实现持久化控制。",
        "disposal_suggestions": ["升级受影响插件到最新版本"],
    }

    cleaned = sanitize_out_of_scope_report(data)

    assert cleaned["attack_chain"] == _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER


def test_sanitize_filters_webshell_disposal_but_keeps_others():
    data = {
        "attack_chain": "无法构建可信攻击链。",
        "disposal_suggestions": [
            "升级受影响插件到最新版本",
            "排查WebShell文件（wp-content/uploads、plugins、themes目录）",
            "核对用户表中的隐藏管理员账户",
        ],
    }

    cleaned = sanitize_out_of_scope_report(data)

    assert cleaned["attack_chain"] == "无法构建可信攻击链。"
    assert cleaned["disposal_suggestions"] == [
        "升级受影响插件到最新版本",
        "核对用户表中的隐藏管理员账户",
    ]


def test_sanitize_fills_placeholder_when_all_disposal_filtered():
    data = {
        "attack_chain": "无法构建可信攻击链。",
        "disposal_suggestions": ["清除WebShell", "查杀后门"],
    }

    cleaned = sanitize_out_of_scope_report(data)

    assert cleaned["disposal_suggestions"] == [_OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER]


def test_sanitize_does_not_mutate_input():
    data = {
        "attack_chain": "攻击者植入后门并持久化。",
        "disposal_suggestions": ["清除WebShell"],
    }

    sanitize_out_of_scope_report(data)

    assert data["attack_chain"] == "攻击者植入后门并持久化。"
    assert data["disposal_suggestions"] == ["清除WebShell"]


def test_sanitize_leaves_clean_report_untouched():
    data = {
        "attack_chain": "告警描述为供应链异常与可疑API请求，未形成完整证据闭环。",
        "disposal_suggestions": ["升级插件", "人工复核事件"],
    }

    cleaned = sanitize_out_of_scope_report(data)

    assert cleaned == data


def test_build_messages_injects_constraint_only_for_out_of_scope():
    agent = DeepInvestigationAgent(config=None, llm=None, tools=None)
    event = SecurityEventInput(event_id="E-1", event_type="WordPress")

    scoped = agent._build_messages(event, gate_decision="out_of_scope")
    weak = agent._build_messages(event, gate_decision="weak_signal")
    none = agent._build_messages(event, gate_decision=None)

    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT in scoped[0]["content"]
    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT not in weak[0]["content"]
    assert _OUT_OF_SCOPE_REPORT_CONSTRAINT not in none[0]["content"]
