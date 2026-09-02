import unittest
from pathlib import Path

from sec_agent.domain.models import (
    ApprovalDecision,
    ApprovalStatus,
    BusinessStatus,
    StartRunRequest,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolRiskLevel,
)
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.orchestrator import Orchestrator


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fixed_alerts"


class JsonlPlatformTest(unittest.TestCase):
    def test_fetch_alerts_maps_normalized_jsonl_to_alert_record(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)

        alerts = adapter.fetch_alerts()

        self.assertEqual(len(alerts), 3)
        sql_injection = alerts[0]
        self.assertEqual(sql_injection.alert_id, "FIX-STA-SQLI-001")
        self.assertEqual(sql_injection.source, "jsonl_sample")
        self.assertEqual(sql_injection.raw_severity, "high")
        self.assertEqual(sql_injection.src_ip, "198.51.100.10")
        self.assertEqual(sql_injection.dst_ip, "198.51.100.20")
        self.assertEqual(sql_injection.assets, ["198.51.100.20"])
        self.assertEqual(sql_injection.scenario_fields["source_device_name"], "STA_001")
        self.assertEqual(sql_injection.scenario_fields["sample_nature"], "platform_derived")

    def test_fetch_alerts_keeps_webshell_critical_rule(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)

        alerts = adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")

        self.assertEqual(len(alerts), 1)
        webshell = alerts[0]
        self.assertEqual(webshell.alert_type, "webshell")
        self.assertEqual(webshell.raw_severity, "critical")
        self.assertEqual(webshell.assets, ["198.51.100.11"])
        self.assertEqual(webshell.scenario_fields["risk_score_seed"], 95)
        self.assertEqual(webshell.scenario_fields["source_device_name"], "XDR")

    def test_fetch_alerts_rejects_unknown_sample(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)

        with self.assertRaisesRegex(ValueError, "JSONL 样例不存在"):
            adapter.fetch_alerts(sample_id="missing-sample")

    def test_evidence_lookup_does_not_depend_on_previous_fetch(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)
        request = ToolRequest(
            trace_id="trace-jsonl",
            event_id="evt-jsonl",
            stage=BusinessStatus.INVESTIGATING,
            tool_name="evidence_lookup",
            action_name="query_related_evidence",
            params={"alert_refs": ["FIX-XDR-WEBSHELL-001"]},
            reason="测试 JSONL 证据查询索引",
            idempotency_key="jsonl-evidence-without-fetch",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )

        result = adapter.run_tool(request)

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertIn("FIX-XDR-WEBSHELL-001:alert_name", result.evidence_refs)

    def test_verify_missing_action_returns_structured_non_success(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)
        request = ToolRequest(
            trace_id="trace-jsonl",
            event_id="evt-jsonl",
            stage=BusinessStatus.VERIFYING,
            tool_name="response_verify",
            action_name="query_action_status",
            params={"idempotency_key": "missing-action"},
            reason="测试未找到处置记录",
            idempotency_key="missing-action",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )

        result = adapter.run_tool(request)

        self.assertEqual(result.status, ToolCallStatus.PARTIAL_SUCCESS)
        self.assertEqual(result.error_type, ToolErrorType.PLATFORM_ERROR)
        self.assertTrue(result.retryable)
        self.assertEqual(result.output_preview["action_status"], "not_found")

    def test_jsonl_webshell_runs_through_approval_flow(self) -> None:
        adapter = JsonlSampleAdapter(FIXTURE_DIR)
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="jsonl_sample", sample_id="FIX-XDR-WEBSHELL-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertIsNotNone(ctx.triage)
        self.assertEqual(ctx.triage.risk_score, 95)
        self.assertIsNotNone(ctx.response)
        self.assertEqual(ctx.response.plan.target, "198.51.100.11")
        self.assertEqual(ctx.response.plan.risk_level, ToolRiskLevel.CRITICAL)

        ctx = orchestrator.approve(
            ctx.event_id,
            ApprovalDecision(
                approved=True,
                approver="tester",
                reason="JSONL 主链联调审批",
                idempotency_key="jsonl-approval-test-001",
            ),
        )

        self.assertEqual(ctx.status, BusinessStatus.COMPLETED)
        self.assertEqual(ctx.response.execution.status, ToolCallStatus.SUCCESS)
        self.assertIsNotNone(ctx.response.verification)
        self.assertEqual(ctx.response.verification.evidence_refs, ["jsonl://actions/jsonl-approval-test-001"])


if __name__ == "__main__":
    unittest.main()
