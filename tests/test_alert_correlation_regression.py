from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path

from sec_agent.domain.models import BusinessStatus, StartRunRequest
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.orchestrator import Orchestrator


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fixed_alerts"


class AlertCorrelationRegressionTest(unittest.TestCase):
    """T0826-06：固定 JSONL 告警接入关联回归。"""

    def setUp(self) -> None:
        self.normalized_adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="normalized")
        self.raw_adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="raw")

    def test_fixed_jsonl_mapping_baseline(self) -> None:
        alerts = {alert.alert_id: alert for alert in self.normalized_adapter.fetch_alerts()}

        sqli = alerts["FIX-STA-SQLI-001"]
        self.assertEqual(sqli.alert_type, "sql_injection")
        self.assertEqual(sqli.raw_severity, "high")
        self.assertEqual(sqli.assets, ["198.51.100.20"])
        self.assertEqual(sqli.scenario_fields["source_device_name"], "STA_001")

        webshell = alerts["FIX-XDR-WEBSHELL-001"]
        self.assertEqual(webshell.alert_type, "webshell")
        self.assertEqual(webshell.raw_severity, "critical")
        self.assertEqual(webshell.assets, ["198.51.100.11"])
        self.assertEqual(webshell.scenario_fields["risk_score_seed"], 95)
        self.assertEqual(webshell.scenario_fields["source_device_name"], "XDR")

        lateral = alerts["FIX-STA-LATERAL-001"]
        self.assertEqual(lateral.alert_type, "lateral_movement")
        self.assertEqual(lateral.raw_severity, "medium")
        self.assertEqual(lateral.scenario_fields["sample_nature"], "synthetic_regression")

    def test_raw_input_keeps_evidence_references_and_correlation_basis(self) -> None:
        webshell = self.raw_adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")[0]

        self.assertEqual(webshell.raw_record_ref, "jsonl://fixed_alerts/raw_alerts.jsonl#FIX-XDR-WEBSHELL-001")
        self.assertIn("FIX-XDR-WEBSHELL-001:alert_name", [ref.ref_id for ref in webshell.evidence_refs])
        self.assertIn("FIX-XDR-WEBSHELL-001:alert_grade", [ref.ref_id for ref in webshell.evidence_refs])

        event = AlertCorrelationService().correlate([webshell])
        self.assertEqual(event.alert_refs, ["FIX-XDR-WEBSHELL-001"])
        self.assertEqual(event.entities["assets"], ["198.51.100.11"])
        self.assertEqual(event.entities["source_devices"], ["XDR"])
        self.assertIn("同一事件类型 webshell", event.correlation_reason)

    def test_exact_fifteen_minute_window_is_accepted(self) -> None:
        original = self.raw_adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")[0]
        duplicate = original.model_copy(
            update={
                "alert_id": "FIX-XDR-WEBSHELL-AT-15M",
                "occurred_at": original.occurred_at + timedelta(minutes=15),
            }
        )

        event = AlertCorrelationService(window_minutes=15).correlate([original, duplicate])

        self.assertEqual(event.alert_count_before, 2)
        self.assertEqual(event.event_count_after, 1)

    def test_over_window_and_conflicting_lookup_are_rejected(self) -> None:
        original = self.raw_adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")[0]
        late_duplicate = original.model_copy(
            update={
                "alert_id": "FIX-XDR-WEBSHELL-OVER-15M",
                "occurred_at": original.occurred_at + timedelta(minutes=15, seconds=1),
            }
        )

        with self.assertRaisesRegex(ValueError, "超出最小关联时间窗口"):
            AlertCorrelationService(window_minutes=15).correlate([original, late_duplicate])
        with self.assertRaisesRegex(ValueError, "sample_id 与 xdr_event_id"):
            self.normalized_adapter.fetch_alerts(
                sample_id="FIX-STA-SQLI-001",
                xdr_event_id="FIX-XDR-WEBSHELL-001",
            )
        with self.assertRaisesRegex(ValueError, "无法关联空告警列表"):
            AlertCorrelationService().correlate([])

    def test_security_event_enters_triage_automatically(self) -> None:
        orchestrator = Orchestrator(
            platform=self.raw_adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="jsonl_sample", sample_id="FIX-XDR-WEBSHELL-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertIsNotNone(ctx.event_summary)
        self.assertIsNotNone(ctx.triage)
        self.assertEqual(ctx.event_summary.alert_refs, ["FIX-XDR-WEBSHELL-001"])
        self.assertEqual(ctx.event_summary.alert_count_before, 1)
        self.assertEqual(ctx.event_summary.event_count_after, 1)
        self.assertEqual(ctx.triage.risk_score, 95)
        self.assertIn(BusinessStatus.TRIAGED, [entry.status for entry in ctx.timeline])


if __name__ == "__main__":
    unittest.main()
