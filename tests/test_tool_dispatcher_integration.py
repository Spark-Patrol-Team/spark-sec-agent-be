import unittest

from sec_agent.domain.models import (
    ApprovalStatus,
    BusinessStatus,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolRiskLevel,
    ToolSideEffectType,
)
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


class ToolDispatcherIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = StatefulMockLedger()
        self.dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=lambda request: ["evidence-test-001"],
            ledger=self.ledger,
            raw_result_prefix="test:/",
            action_ref_prefix="test:/",
            source_label="测试平台",
        )

    def test_dispatcher_runs_main_flow_tools(self) -> None:
        evidence_result = self.dispatcher.dispatch(
            self._request(
                tool_name="evidence_lookup",
                action_name="query_related_evidence",
                stage=BusinessStatus.INVESTIGATING,
                risk_level=ToolRiskLevel.LOW,
            )
        )

        execute_result = self.dispatcher.dispatch(
            self._request(
                tool_name="stateful_response_mock",
                action_name="stateful_mock_containment",
                stage=BusinessStatus.EXECUTING,
                risk_level=ToolRiskLevel.HIGH,
                dry_run=False,
                approval_status=ApprovalStatus.APPROVED,
                params={"event_id": "evt-test", "target": "asset-test"},
            )
        )

        verify_result = self.dispatcher.dispatch(
            self._request(
                tool_name="response_verify",
                action_name="query_action_status",
                stage=BusinessStatus.VERIFYING,
                risk_level=ToolRiskLevel.LOW,
            )
        )

        self.assertEqual(evidence_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(evidence_result.evidence_refs, ["evidence-test-001"])
        self.assertEqual(evidence_result.raw_result_ref, f"test://tools/evidence_lookup/{evidence_result.call_id}")
        self.assertEqual(execute_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(execute_result.side_effect_type, ToolSideEffectType.STATE_CHANGE)
        self.assertEqual(verify_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(verify_result.evidence_refs, ["test://actions/tool-dispatcher-test"])

    def test_dispatcher_keeps_legacy_xdr_log_query_available(self) -> None:
        result = self.dispatcher.dispatch(
            self._request(
                tool_name="xdr_log_query",
                action_name="query_builtin_xdr_log",
                stage=BusinessStatus.INVESTIGATING,
                risk_level=ToolRiskLevel.LOW,
            )
        )

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertIn("records", result.output_preview)

    def test_dispatcher_returns_structured_error_for_unknown_tool(self) -> None:
        result = self.dispatcher.dispatch(
            self._request(
                tool_name="unknown_tool",
                action_name="unknown_action",
                stage=BusinessStatus.INVESTIGATING,
                risk_level=ToolRiskLevel.LOW,
            )
        )

        self.assertEqual(result.status, ToolCallStatus.FAILED)
        self.assertEqual(result.error_type, ToolErrorType.UNSUPPORTED_TOOL)
        self.assertTrue(result.retryable)

    def _request(
        self,
        *,
        tool_name: str,
        action_name: str,
        stage: BusinessStatus,
        risk_level: ToolRiskLevel,
        dry_run: bool = True,
        approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED,
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


if __name__ == "__main__":
    unittest.main()
