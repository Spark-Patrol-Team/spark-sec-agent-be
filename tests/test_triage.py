from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sec_agent.domain.models import AlertRecord, EvidenceRef, Priority, SecurityEvent, TruthVerdict
from sec_agent.services.triage import RiskTriageService


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


if __name__ == "__main__":
    unittest.main()
