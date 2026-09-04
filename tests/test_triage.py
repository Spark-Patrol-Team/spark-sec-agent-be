from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sec_agent.domain.models import AlertRecord, EvidenceRef, Priority, SecurityEvent, TruthVerdict
from sec_agent.services.triage import RiskTriageService, VERDICT_CONFIDENCE


def make_alert(
    alert_id: str,
    severity: str,
    alert_type: str,
    seed: int | None = None,
    with_evidence: bool = True,
) -> AlertRecord:
    evidence_refs = (
        [EvidenceRef(ref_id=f"{alert_id}-ev1", source="test", kind="http", summary="测试证据")]
        if with_evidence
        else []
    )
    scenario_fields = {"risk_score_seed": seed} if seed is not None else {}
    return AlertRecord(
        alert_id=alert_id,
        source="test",
        occurred_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        name=f"测试告警-{alert_id}",
        alert_type=alert_type,
        raw_severity=severity,
        scenario_fields=scenario_fields,
        evidence_refs=evidence_refs,
        raw_record_ref=f"test://{alert_id}",
    )


def make_event(alerts: list[AlertRecord], alert_count_before: int | None = None) -> SecurityEvent:
    return SecurityEvent(
        event_id="evt-test",
        alert_refs=[alert.alert_id for alert in alerts],
        first_seen_at=datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 21, 9, 5, tzinfo=timezone.utc),
        correlation_reason="测试关联",
        alert_count_before=alert_count_before if alert_count_before is not None else len(alerts),
        event_count_after=1,
        summary="测试事件",
    )


class RiskTriageServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RiskTriageService()

    def test_webshell_critical_seed_yields_malicious_high(self) -> None:
        alert = make_alert("a1", "critical", "webshell", seed=95)
        result = self.service.triage(make_event([alert]), [alert])

        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.priority, Priority.HIGH)
        self.assertEqual(result.risk_score, 95)
        self.assertTrue(result.should_investigate)

    def test_sql_injection_high_seed_yields_malicious(self) -> None:
        alert = make_alert("a1", "high", "sql_injection", seed=80)
        result = self.service.triage(make_event([alert]), [alert])

        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.risk_score, 80)

    def test_lateral_medium_seed_yields_uncertain_medium(self) -> None:
        alert = make_alert("a1", "medium", "lateral_movement", seed=65)
        result = self.service.triage(make_event([alert]), [alert])

        self.assertEqual(result.verdict, TruthVerdict.UNCERTAIN)
        self.assertEqual(result.priority, Priority.MEDIUM)
        self.assertEqual(result.risk_score, 65)
        self.assertTrue(result.should_investigate)

    def test_low_benign_no_seed_does_not_investigate(self) -> None:
        alert = make_alert("a1", "low", "other", seed=None)
        result = self.service.triage(make_event([alert]), [alert])

        self.assertEqual(result.verdict, TruthVerdict.BENIGN)
        self.assertEqual(result.priority, Priority.LOW)
        self.assertFalse(result.should_investigate)
        self.assertLess(result.risk_score, 40)

    def test_correlation_bonus_for_multiple_alerts(self) -> None:
        alerts = [
            make_alert("a1", "high", "webshell"),
            make_alert("a2", "high", "webshell"),
        ]
        result = self.service.triage(make_event(alerts, alert_count_before=2), alerts)

        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.risk_score, 85)

    def test_missing_evidence_records_gap(self) -> None:
        alert = make_alert("a1", "medium", "lateral_movement", seed=65, with_evidence=False)
        result = self.service.triage(make_event([alert]), [alert])

        self.assertIn("缺少可定位的原始证据引用", result.evidence_gaps)

    def test_empty_alerts_yields_benign_zero(self) -> None:
        result = self.service.triage(make_event([], alert_count_before=0), [])

        self.assertEqual(result.verdict, TruthVerdict.BENIGN)
        self.assertEqual(result.risk_score, 0)
        self.assertFalse(result.should_investigate)

    def test_same_input_is_deterministic(self) -> None:
        alert = make_alert("a1", "critical", "webshell", seed=95)
        first = self.service.triage(make_event([alert]), [alert])
        second = self.service.triage(make_event([alert]), [alert])

        self.assertEqual(first.model_dump(), second.model_dump())

    # ---- 边界测试（T0827-07）：缺失严重度 / 未知攻击类型 / 证据不足 / 阈值边界 / 需调查条件 ----

    def test_unknown_severity_contributes_zero(self) -> None:
        # 严重度字符串不在映射表（含空串、中文等级、大小写/空白），应计 0 分，仅剩攻击类型分。
        for unknown_severity in ("未知", "", "高危", " HIGH "):
            with self.subTest(severity=unknown_severity):
                alert = make_alert("a1", unknown_severity, "webshell")
                result = self.service.triage(make_event([alert]), [alert])
                # 攻击类型 webshell=30，严重度被忽略，且无关联加成/种子分。
                self.assertEqual(result.risk_score, 30)
                self.assertEqual(result.verdict, TruthVerdict.BENIGN)
                self.assertFalse(result.should_investigate)

    def test_unknown_attack_type_contributes_zero(self) -> None:
        # 攻击类型不在映射表（"other"/未知值），应计 0 分，仅剩严重度分。
        for unknown_type in ("ransomware", "unknown_type", "other"):
            with self.subTest(alert_type=unknown_type):
                alert = make_alert("a1", "low", unknown_type)
                result = self.service.triage(make_event([alert]), [alert])
                # 严重度 low=10，攻击类型被忽略，无关联加成/种子分。
                self.assertEqual(result.risk_score, 10)
                self.assertEqual(result.verdict, TruthVerdict.BENIGN)
                self.assertFalse(result.should_investigate)

    def test_missing_severity_and_unknown_type_collapses_to_zero(self) -> None:
        # 严重度与攻击类型均未映射：rule_score 归零，无种子分时为 benign 0。
        alert = make_alert("a1", "未知", "ransomware", with_evidence=False)
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 0)
        self.assertEqual(result.verdict, TruthVerdict.BENIGN)
        self.assertFalse(result.should_investigate)
        self.assertIn("缺少可定位的原始证据引用", result.evidence_gaps)

    def test_threshold_exactly_70_is_malicious(self) -> None:
        # 阈值上边界：risk_score == 70 必须判定为 malicious/high/进入调查。
        alert = make_alert("a1", "high", "webshell")  # 40 + 30 = 70
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 70)
        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.priority, Priority.HIGH)
        self.assertTrue(result.should_investigate)

    def test_threshold_just_below_70_is_uncertain(self) -> None:
        # 69（<70）落到 uncertain/medium，且仍进入调查。
        alert = make_alert("a1", "low", "unknown_type", seed=69)
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 69)
        self.assertEqual(result.verdict, TruthVerdict.UNCERTAIN)
        self.assertEqual(result.priority, Priority.MEDIUM)
        self.assertTrue(result.should_investigate)

    def test_threshold_exactly_40_is_uncertain_investigates(self) -> None:
        # 阈值下边界：risk_score == 40 判定为 uncertain/medium/进入调查。
        alert = make_alert("a1", "medium", "lateral_movement")  # 20 + 20 = 40
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 40)
        self.assertEqual(result.verdict, TruthVerdict.UNCERTAIN)
        self.assertEqual(result.priority, Priority.MEDIUM)
        self.assertTrue(result.should_investigate)

    def test_threshold_just_below_40_is_benign(self) -> None:
        # 39（<40）落到 benign/low/不调查。
        alert = make_alert("a1", "low", "unknown_type", seed=39)
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 39)
        self.assertEqual(result.verdict, TruthVerdict.BENIGN)
        self.assertEqual(result.priority, Priority.LOW)
        self.assertFalse(result.should_investigate)

    def test_confidence_matches_verdict_tiers(self) -> None:
        # 置信度为按结论的固定档位：confidence 只随 verdict 走，与分数/证据无关。
        malicious = self.service.triage(
            make_event([make_alert("a1", "high", "webshell")]), [make_alert("a1", "high", "webshell")]
        )
        uncertain = self.service.triage(
            make_event([make_alert("a1", "medium", "lateral_movement")]), [make_alert("a1", "medium", "lateral_movement")]
        )
        benign = self.service.triage(
            make_event([make_alert("a1", "low", "unknown_type")]), [make_alert("a1", "low", "unknown_type")]
        )
        for result in (malicious, uncertain, benign):
            self.assertEqual(result.confidence, VERDICT_CONFIDENCE[result.verdict])
        self.assertEqual(malicious.confidence, 0.85)
        self.assertEqual(uncertain.confidence, 0.65)
        self.assertEqual(benign.confidence, 0.70)

    def test_non_benign_always_investigates(self) -> None:
        # 需调查条件：应进入调查当且仅当 verdict 非 benign。
        malicious = self.service.triage(
            make_event([make_alert("a1", "high", "webshell")]), [make_alert("a1", "high", "webshell")]
        )
        uncertain = self.service.triage(
            make_event([make_alert("a1", "medium", "lateral_movement")]), [make_alert("a1", "medium", "lateral_movement")]
        )
        benign = self.service.triage(
            make_event([make_alert("a1", "low", "unknown_type")]), [make_alert("a1", "low", "unknown_type")]
        )
        self.assertTrue(malicious.should_investigate)
        self.assertTrue(uncertain.should_investigate)
        self.assertFalse(benign.should_investigate)

    def test_uncertain_without_evidence_has_both_gaps(self) -> None:
        # 证据不足且判定为 uncertain：应同时给出「证据缺口」与「需补充上下文」两条。
        alert = make_alert("a1", "medium", "lateral_movement", with_evidence=False)
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.risk_score, 40)
        self.assertEqual(result.verdict, TruthVerdict.UNCERTAIN)
        self.assertIn("缺少可定位的原始证据引用", result.evidence_gaps)
        self.assertIn("需要补充平台侧日志或上下文", result.evidence_gaps)

    def test_evidence_present_has_no_gap(self) -> None:
        # 有证据且非 uncertain：evidence_gaps 为空。
        alert = make_alert("a1", "high", "webshell")
        result = self.service.triage(make_event([alert]), [alert])
        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.evidence_gaps, [])

    def test_correlation_bonus_crosses_high_threshold(self) -> None:
        # 关联加成能把 60 分推过 70 阈值：2 条 high+sql_injection（40+20）+15=75。
        alerts = [
            make_alert("a1", "high", "sql_injection"),
            make_alert("a2", "high", "sql_injection"),
        ]
        result = self.service.triage(make_event(alerts, alert_count_before=2), alerts)
        self.assertEqual(result.risk_score, 75)
        self.assertEqual(result.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(result.priority, Priority.HIGH)
        self.assertTrue(result.should_investigate)


if __name__ == "__main__":
    unittest.main()
