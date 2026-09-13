# -*- coding: utf-8 -*-
"""《事件字段—来源—信号强度合同》v1.1 的代码一致性测试。

负责人/执行人：陈敏（登记方）
日期：2026-09-13
合同文档：docs/modules/alert-correlation/event-field-signal-contract.md
基线：`main@0001bbd`（PR #50 已合入；合同 §5 D1 已由 `38cee87 fix: address PR50 review findings`
按“稳定引用 ID + 摘要映射”实现，本轮由 xfail 转为通过）

本文件只验证“主链是否按合同理解字段”，不重复验证门禁自身的判定规则
（判定规则由 tests/test_gatekeeper_boundary.py 与 tests/test_gatekeeper_case1_10.py 覆盖）。

已冻结部分（对齐即通过）：
- `event_type` 由告警类型产生，是机器契约字段，不再由面向人的 `summary` 反推；
- `alert_summaries` / `evidence_summaries` 均以稳定引用 ID 为键，禁止按数组下标拼接；
- 无摘要证据不进入映射，桥接仍保留其原始 ID；
- 门禁只读取白名单字段，空字段安全降级；
- D1：证据 ID 与摘要一一对应，覆盖“新的在前”入参顺序与空摘要两种错位场景。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.deep_agent_bridge import DeepAgentBridge
from sec_agent.services.gatekeeper import (
    GATEKEEPER_WHITELIST_FIELDS,
    GateDecision,
    WebShellGatekeeper,
)
from sec_agent.services.triage import RiskTriageService


CONTRACT_VERSION = "v1.1"
KNOWN_TYPES = {"webshell", "sql_injection", "lateral_movement", "unauthorized_access", "other"}
REF_SEPARATOR = ": "

# 合同 §1 声明的两套字段面，必须与代码一致（含 summary 不在任何一侧）。
CONTRACT_AGENT_INPUT_FIELDS = {
    "event_id",
    "event_type",
    "severity",
    "timestamp",
    "source_ip",
    "target_ip",
    "alerts",
    "evidence",
    "initial_verdict",
    "confidence",
    "triage",
    "trace_id",
    "run_id",
}
CONTRACT_GATE_WHITELIST_FIELDS = {
    "event_id",
    "event_type",
    "severity",
    "timestamp",
    "source_ip",
    "target_ip",
    "alerts",
    "evidence",
    "triage",
    "initial_verdict",
}
FORBIDDEN_GATE_FIELDS = {"confidence", "trace_id", "run_id"}


def _fixed_sample_alerts():
    return FixedSampleAdapter().fetch_alerts(sample_id="webshell-001")


def _chain(alerts):
    event = AlertCorrelationService().correlate(alerts)
    triage = RiskTriageService().triage(event, alerts)
    payload = DeepAgentBridge()._to_deep_agent_input(trace_id="trace", run_id="run", event=event, triage=triage)
    return event, triage, payload


def _alert_truth(alerts) -> dict[str, str]:
    return {alert.alert_id: alert.name for alert in alerts}


def _evidence_truth(alerts) -> dict[str, str]:
    """以告警自带的 evidence_refs 为基准，构造 ref_id → summary 的真实映射。"""
    return {ref.ref_id: (ref.summary or "") for alert in alerts for ref in alert.evidence_refs}


def _split(payload_item: str) -> tuple[str, str]:
    head, _, tail = payload_item.partition(REF_SEPARATOR)
    return head, tail


class TestContractVersionAndFields:
    def test_event_type_is_machine_token_from_alert_type(self) -> None:
        alerts = _fixed_sample_alerts()
        event, _, payload = _chain(alerts)

        assert event.event_type == alerts[0].alert_type
        assert event.event_type.lower() in KNOWN_TYPES
        assert payload["event_type"] == event.event_type

    def test_event_type_is_not_guessed_from_human_summary(self) -> None:
        alerts = _fixed_sample_alerts()
        event, _, payload = _chain(alerts)

        assert event.summary and event.summary != event.event_type
        assert payload["event_type"] != event.summary, "主链不得再用 summary 猜事件类型"

    def test_alert_summaries_are_keyed_by_alert_id(self) -> None:
        alerts = _fixed_sample_alerts()
        event, _, _ = _chain(alerts)
        truth = _alert_truth(alerts)

        assert set(event.alert_summaries) == set(event.alert_refs)
        for ref in event.alert_refs:
            assert event.alert_summaries[ref] == truth[ref], "告警摘要必须与自己的 ID 绑定"

    def test_alert_payload_pairs_each_id_with_its_own_summary(self) -> None:
        alerts = _fixed_sample_alerts()
        _, _, payload = _chain(alerts)
        truth = _alert_truth(alerts)

        for item in payload["alerts"]:
            ref, summary = _split(item)
            assert truth.get(ref) == summary, f"告警 {ref} 被贴上了别人的摘要"

    def test_evidence_summaries_are_keyed_by_ref_id(self) -> None:
        alerts = _fixed_sample_alerts()
        event, _, _ = _chain(alerts)
        truth = _evidence_truth(alerts)

        assert set(event.evidence_summaries) <= set(truth)
        for ref, summary in event.evidence_summaries.items():
            assert summary == truth[ref], "证据摘要必须与自己的 ref_id 绑定"
        assert all(event.evidence_summaries.values()), "空摘要不应进入映射"

    def test_event_type_and_summaries_survive_domain_model_round_trip(self) -> None:
        event, _, payload = _chain(_fixed_sample_alerts())
        restored = type(event).model_validate(event.model_dump(mode="json"))

        assert restored.event_type == event.event_type
        assert restored.alert_summaries == event.alert_summaries
        assert restored.evidence_summaries == event.evidence_summaries
        assert payload["event_type"] == restored.event_type


class TestGateFieldProvenance:
    def test_agent_input_field_surface_matches_contract(self) -> None:
        """SecurityEventInput 必须恰好是合同 §1 声明的 13 字段，且不含 summary。"""
        fields = {f.name for f in dataclasses.fields(SecurityEventInput)}

        assert fields == CONTRACT_AGENT_INPUT_FIELDS
        assert "summary" not in fields, "summary 是 SecurityEvent 字段，不进入 Agent 输入"

    def test_gate_whitelist_surface_matches_contract(self) -> None:
        """门禁白名单必须恰好是合同 §1 声明的 10 字段，且 summary 不在其中。"""
        whitelist = set(GATEKEEPER_WHITELIST_FIELDS)
        fields = {f.name for f in dataclasses.fields(SecurityEventInput)}

        assert whitelist == CONTRACT_GATE_WHITELIST_FIELDS
        assert "summary" not in whitelist, "门禁白名单不得包含 summary"
        assert whitelist <= fields, "白名单不得出现 Agent 输入之外的字段"
        assert fields - whitelist == FORBIDDEN_GATE_FIELDS

    def test_bridge_output_matches_agent_input_contract(self) -> None:
        """bridge 产出的 payload 键集合必须等于 13 字段契约，不得夹带 summary 等域模型字段。"""
        _, _, payload = _chain(_fixed_sample_alerts())
        fields = {f.name for f in dataclasses.fields(SecurityEventInput)}

        assert set(payload) == fields
        assert "summary" not in payload
        assert "alert_refs" not in payload and "evidence_summaries" not in payload

    def test_gate_cannot_read_summary_even_when_present_in_payload(self) -> None:
        """即便调用方硬塞 summary，门禁也拿不到它（不在白名单即被 filter_input 丢弃）。"""
        gate = WebShellGatekeeper()
        raw = dict.fromkeys(CONTRACT_AGENT_INPUT_FIELDS, "")
        raw["summary"] = "已将 1 条 webshell 告警压缩为 1 个安全事件"
        raw["alerts"] = []
        raw["evidence"] = []

        assert gate.filter_input(raw).get("summary") is None
        result = gate.audit(SecurityEventInput.from_dict(raw))
        assert not any("webshell" in str(signal.description).lower() for signal in result.signals)

    def test_gate_decision_uses_machine_event_type_on_main_chain(self) -> None:
        _, _, payload = _chain(_fixed_sample_alerts())
        result = WebShellGatekeeper().audit(SecurityEventInput.from_dict(payload))

        assert result.gate_decision == GateDecision.IN_SCOPE
        assert any(
            signal.source.value == "event_type" for signal in result.signals
        ), "主链事件类型必须作为独立信号来源参与判定"

    def test_empty_type_and_containers_fail_closed_on_main_chain(self) -> None:
        result = WebShellGatekeeper().audit(SecurityEventInput.from_dict({}))

        assert result.gate_decision == GateDecision.WEAK_SIGNAL
        assert result.gate_decision != GateDecision.IN_SCOPE


class TestEvidencePairingById:
    """合同 §5 D1（已在 main 实现）：证据 ID 与摘要必须一一对应，避免证据串位。"""

    def test_evidence_refs_and_summaries_are_aligned_by_id(self) -> None:
        base = datetime.fromisoformat("2026-09-01T10:00:00+08:00")
        first, second = _fixed_sample_alerts()
        # 模拟 XDR 分页“新的在前”的入参顺序：入参顺序 ≠ occurred_at 升序
        alerts = [
            first.model_copy(update={"occurred_at": base + timedelta(minutes=10)}),
            second.model_copy(update={"occurred_at": base + timedelta(minutes=5)}),
        ]
        truth = _evidence_truth(alerts)

        _, _, payload = _chain(alerts)

        for item in payload["evidence"]:
            ref_id, summary = _split(item)
            assert truth.get(ref_id) == summary, (
                f"合同 {CONTRACT_VERSION} §5 D1：evidence {ref_id} 被贴上了别人的摘要"
            )

    def test_evidence_without_summary_keeps_its_own_ref_id(self) -> None:
        alerts = _fixed_sample_alerts()
        stripped = alerts[0].model_copy(
            update={
                "evidence_refs": [
                    ref.model_copy(update={"summary": None}) for ref in alerts[0].evidence_refs
                ]
            }
        )
        truth = _evidence_truth([stripped, alerts[1]])

        _, _, payload = _chain([stripped, alerts[1]])

        for item in payload["evidence"]:
            ref_id, summary = _split(item)
            expected = truth.get(ref_id)
            if expected:
                assert summary == expected, f"合同 {CONTRACT_VERSION} §5 D1：{ref_id} 摘要错位"
            else:
                assert item == ref_id, "无摘要证据必须只保留原始 ID，不得借用他人摘要"
