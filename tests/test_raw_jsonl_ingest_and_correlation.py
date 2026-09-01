from __future__ import annotations

import json
import unittest
from datetime import timedelta
from pathlib import Path

from sec_agent.domain.models import (
    ApprovalDecision,
    BusinessStatus,
    NormalizedAlertRecord,
    StartRunRequest,
)
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
from sec_agent.platforms.raw_jsonl import RawJsonlNormalizer
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.orchestrator import Orchestrator


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fixed_alerts"
RAW_FILE = FIXTURE_DIR / "raw_alerts.jsonl"
NORMALIZED_FILE = FIXTURE_DIR / "normalized_alerts.jsonl"


class RawJsonlIngestAndCorrelationTest(unittest.TestCase):
    def test_raw_jsonl_normalization_matches_committed_contract(self) -> None:
        actual = RawJsonlNormalizer().load_jsonl(RAW_FILE)
        expected = [
            NormalizedAlertRecord.model_validate(json.loads(line))
            for line in NORMALIZED_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(
            [record.model_dump(mode="json") for record in actual],
            [record.model_dump(mode="json") for record in expected],
        )

    def test_raw_jsonl_adapter_preserves_webshell_override_and_asset_priority(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="raw")

        alerts = adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")

        self.assertEqual(len(alerts), 1)
        webshell = alerts[0]
        self.assertEqual(webshell.alert_type, "webshell")
        self.assertEqual(webshell.raw_severity, "critical")
        self.assertEqual(webshell.assets, ["198.51.100.11"])
        self.assertEqual(webshell.scenario_fields["risk_score_seed"], 95)
        self.assertEqual(webshell.scenario_fields["source_device_name"], "XDR")
        self.assertEqual(webshell.raw_record_ref, "jsonl://fixed_alerts/raw_alerts.jsonl#FIX-XDR-WEBSHELL-001")

    def test_destination_missing_uses_host_ip_only_as_fallback(self) -> None:
        raw = {
            "sample_id": "FIX-XDR-FALLBACK-001",
            "sample_nature": "platform_derived",
            "sample_source": "XDR 安全告警分析",
            "alert_time": "2026-08-22 10:00:00",
            "alert_name": "WebShell回退验证",
            "alert_grade": "高危",
            "source_ip": "198.51.100.50",
            "destination_ip": None,
            "host_ip": "198.51.100.66",
            "data_source": "XDR",
            "source_device_name": "XDR",
        }

        record = RawJsonlNormalizer().normalize(raw)

        self.assertEqual(record.destination_ip, "198.51.100.66")
        self.assertEqual(record.affected_asset, "198.51.100.66")
        self.assertEqual(record.severity, "high")
        self.assertEqual(record.risk_score_seed, 80)

    def test_duplicate_alerts_are_compressed_with_explicit_basis(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="raw")
        original = adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")[0]
        duplicate = original.model_copy(
            update={
                "alert_id": "FIX-XDR-WEBSHELL-002",
                "occurred_at": original.occurred_at + timedelta(minutes=2),
            }
        )

        event = AlertCorrelationService(window_minutes=15).correlate([duplicate, original])

        self.assertEqual(event.alert_count_before, 2)
        self.assertEqual(event.event_count_after, 1)
        self.assertEqual(event.alert_refs, ["FIX-XDR-WEBSHELL-001", "FIX-XDR-WEBSHELL-002"])
        self.assertEqual(event.entities["assets"], ["198.51.100.11"])
        self.assertEqual(event.entities["source_devices"], ["XDR"])
        self.assertIn("同一事件类型 webshell", event.correlation_reason)
        self.assertIn("不超过 15 分钟", event.correlation_reason)

    def test_unrelated_alerts_are_rejected_for_single_event_correlation(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="raw")
        webshell = adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")[0]
        lateral = adapter.fetch_alerts(sample_id="FIX-STA-LATERAL-001")[0]

        with self.assertRaisesRegex(ValueError, "事件类型不一致"):
            AlertCorrelationService().correlate([webshell, lateral])

    def test_raw_jsonl_webshell_reaches_approval_gate(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR, input_mode="raw")
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="jsonl_sample", sample_id="FIX-XDR-WEBSHELL-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertIsNotNone(ctx.event_summary)
        self.assertEqual(ctx.event_summary.alert_count_before, 1)
        self.assertEqual(ctx.event_summary.event_count_after, 1)
        self.assertEqual(ctx.triage.risk_score, 95)

        completed = orchestrator.approve(
            ctx.event_id,
            ApprovalDecision(
                approved=True,
                approver="chenmin-test",
                reason="验证原始 JSONL 标准化输入能够进入完整最小主链",
                idempotency_key="raw-jsonl-webshell-approval-001",
            ),
        )
        self.assertEqual(completed.status, BusinessStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
