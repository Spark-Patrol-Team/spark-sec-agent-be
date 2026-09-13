# -*- coding: utf-8 -*-
"""《事件字段—来源—信号强度合同》v1.0 的代码一致性测试。

负责人/执行人：陈敏（登记方）
日期：2026-09-13
合同文档：docs/modules/alert-correlation/event-field-signal-contract.md

本文件只验证“主链是否按合同理解字段”，不重复验证门禁自身的判定规则
（判定规则由 tests/test_gatekeeper_boundary.py 与 tests/test_gatekeeper_case1_10.py 覆盖）。

已冻结部分（对齐即通过）：
- event_type 由告警类型产生，是机器契约字段，不再由面向人的 summary 反推；
- alert_refs 与 alert_summaries 同长同序，按位置一一对应；
- 门禁只读取白名单字段，空字段安全降级。

待冻结部分（contract §5 D1）：supporting_evidence_refs 与 evidence_summaries
当前由两个不同排序来源产生，桥接按位置配对会产生证据串位，因此该项以 xfail 记录，
修好之后会自动转为 xpass，提醒双方同步更新合同版本。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.deep_agent_bridge import DeepAgentBridge
from sec_agent.services.gatekeeper import GateDecision, WebShellGatekeeper
from sec_agent.services.triage import RiskTriageService


CONTRACT_VERSION = "v1.0"
KNOWN_TYPES = {"webshell", "sql_injection", "lateral_movement", "unauthorized_access", "other"}


def _fixed_sample_alerts():
    return FixedSampleAdapter().fetch_alerts(sample_id="webshell-001")


def _chain(alerts):
    event = AlertCorrelationService().correlate(alerts)
    triage = RiskTriageService().triage(event, alerts)
    payload = DeepAgentBridge()._to_deep_agent_input(trace_id="trace", run_id="run", event=event, triage=triage)
    return event, triage, payload


def _evidence_truth(alerts) -> dict[str, str]:
    """以告警自带的 evidence_refs 为基准，构造 ref_id → summary 的真实映射。"""
    return {ref.ref_id: (ref.summary or "") for alert in alerts for ref in alert.evidence_refs}


def _split(payload_item: str) -> tuple[str, str]:
    head, _, tail = payload_item.partition(": ")
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

    def test_alert_refs_and_alert_summaries_are_aligned(self) -> None:
        alerts = _fixed_sample_alerts()
        event, _, payload = _chain(alerts)

        assert event.alert_refs == [alert.alert_id for alert in alerts]
        assert event.alert_summaries == [alert.name for alert in alerts]
        assert len(event.alert_refs) == len(event.alert_summaries)
        for item, alert_id, name in zip(payload["alerts"], event.alert_refs, event.alert_summaries):
            assert item == f"{alert_id}: {name}"

    def test_event_type_and_summaries_survive_domain_model_round_trip(self) -> None:
        event, _, payload = _chain(_fixed_sample_alerts())
        restored = type(event).model_validate(event.model_dump(mode="json"))

        assert restored.event_type == event.event_type
        assert restored.alert_summaries == event.alert_summaries
        assert restored.evidence_summaries == event.evidence_summaries
        assert payload["event_type"] == restored.event_type


class TestGateFieldProvenance:
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


class TestEvidencePairingFreezeItem:
    """合同 §5 D1：证据 ID 与摘要必须一一对应，避免证据串位。"""

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "合同 v1.0 §5 D1 未冻结：deep_agent_bridge._described_refs 目前按位置配对，"
            "correlation 按 occurred_at 排序、triage 按入参顺序，两者不一致时会证据串位。"
        ),
    )
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

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "合同 v1.0 §5 D1 未冻结：correlation 会过滤空摘要，导致后续证据整体串位。"
        ),
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
            assert truth.get(ref_id) == summary, (
                f"合同 {CONTRACT_VERSION} §5 D1：空摘要证据 {ref_id} 被贴上了别人的摘要"
            )
