import unittest

from sec_agent.domain.models import (
    ApprovalStatus,
    BusinessStatus,
    InvestigationReport,
    Priority,
    SecurityEvent,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolRiskLevel,
    TriageResult,
    TruthVerdict,
)
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.services.deep_agent_bridge import DeepAgentBridgeUnavailable
from sec_agent.services.investigation import DeepInvestigationAgent
from sec_agent.services.response import ResponseDecisionService
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


class InvestigationAndDispatcherIntegrationTest(unittest.TestCase):
    def test_auto_backend_records_fallback_and_runs_internal_tool_chain(self) -> None:
        service = DeepInvestigationAgent(platform=FixedSampleAdapter(), backend="auto")
        service._deep_agent_bridge = _UnavailableBridge()

        report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")

        self.assertFalse(report.needs_human)
        self.assertIn("已回退内部工具调查子链", report.summary)
        self.assertTrue(any("deep_agent 不可用" in item for item in report.unresolved_questions))
        self.assertEqual(
            [step.tool_request.tool_name for step in report.steps if step.tool_request],
            ["evidence_lookup", "xdr_log_query"],
        )
        self.assertEqual(len(report.tool_results), 2)

    def test_platform_dispatcher_supports_main_chain_tools(self) -> None:
        ledger = StatefulMockLedger()
        dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=lambda request: ["evidence-test-001"],
            ledger=ledger,
            raw_result_prefix="test://tools",
            action_ref_prefix="test://actions",
            source_label="测试平台",
        )

        evidence_result = dispatcher.dispatch(
            self._request(
                tool_name="evidence_lookup",
                action_name="query_related_evidence",
                stage=BusinessStatus.INVESTIGATING,
            )
        )
        xdr_result = dispatcher.dispatch(
            self._request(
                tool_name="xdr_log_query",
                action_name="query_builtin_xdr_log",
                stage=BusinessStatus.INVESTIGATING,
            )
        )
        execute_result = dispatcher.dispatch(
            self._request(
                tool_name="stateful_response_mock",
                action_name="stateful_mock_containment",
                stage=BusinessStatus.EXECUTING,
                dry_run=False,
                approval_status=ApprovalStatus.APPROVED,
                risk_level=ToolRiskLevel.HIGH,
                params={"event_id": "evt-test", "target": "asset-test"},
            )
        )
        verify_result = dispatcher.dispatch(
            self._request(
                tool_name="response_verify",
                action_name="query_action_status",
                stage=BusinessStatus.VERIFYING,
            )
        )

        self.assertEqual(evidence_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(evidence_result.evidence_refs, ["evidence-test-001"])
        self.assertEqual(xdr_result.status, ToolCallStatus.SUCCESS)
        self.assertIn("records", xdr_result.output_preview)
        self.assertEqual(execute_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(verify_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(verify_result.evidence_refs, ["test://actions/tool-dispatcher-test"])

    def test_dispatcher_returns_structured_error_for_unknown_tool(self) -> None:
        dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=lambda request: [],
            ledger=StatefulMockLedger(),
            raw_result_prefix="test://tools",
            action_ref_prefix="test://actions",
            source_label="测试平台",
        )

        result = dispatcher.dispatch(
            self._request(
                tool_name="unknown_tool",
                action_name="unknown_action",
                stage=BusinessStatus.INVESTIGATING,
            )
        )

        self.assertEqual(result.status, ToolCallStatus.FAILED)
        self.assertEqual(result.error_type, ToolErrorType.UNSUPPORTED_TOOL)
        self.assertTrue(result.retryable)

    def test_response_plan_requires_explicit_target(self) -> None:
        report = InvestigationReport(
            conclusion=TruthVerdict.MALICIOUS,
            final_confidence=0.9,
            affected_objects=[],
            recommended_actions=["阻断可疑源 IP 或会话"],
            needs_human=False,
            summary="测试报告",
        )

        plan = ResponseDecisionService().build_plan(report, self._triage())

        self.assertIsNone(plan)

    def _request(
        self,
        *,
        tool_name: str,
        action_name: str,
        stage: BusinessStatus,
        dry_run: bool = True,
        approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED,
        risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
        params: dict | None = None,
    ) -> ToolRequest:
        return ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=stage,
            tool_name=tool_name,
            action_name=action_name,
            params=params or {},
            reason="测试工具调度集成",
            dry_run=dry_run,
            idempotency_key="tool-dispatcher-test",
            risk_level=risk_level,
            approval_status=approval_status,
        )

    def _event(self) -> SecurityEvent:
        return SecurityEvent(
            event_id="evt-test",
            alert_refs=["xdr-alert-001", "xdr-alert-002"],
            first_seen_at=__import__("datetime").datetime.fromisoformat("2026-08-20T14:21:15+08:00"),
            last_seen_at=__import__("datetime").datetime.fromisoformat("2026-08-20T14:21:15+08:00"),
            entities={"src_ips": ["10.10.2.15"], "dst_ips": ["172.16.8.21"], "assets": ["web-server-01"]},
            correlation_reason="测试关联",
            alert_count_before=2,
            event_count_after=1,
            summary="WebShell 高危事件",
        )

    def _triage(self) -> TriageResult:
        return TriageResult(
            verdict=TruthVerdict.MALICIOUS,
            confidence=0.85,
            risk_score=95,
            priority=Priority.HIGH,
            supporting_evidence_refs=["evidence-http-001"],
            should_investigate=True,
            summary="高风险，需要深度调查",
        )


class _UnavailableBridge:
    def investigate(self, trace_id, run_id, event, triage):
        raise DeepAgentBridgeUnavailable("单元测试模拟 deep_agent 缺失")


if __name__ == "__main__":
    unittest.main()
