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
from sec_agent.platforms.fixed_sample import FixedSampleAdapter


class ToolContractTest(unittest.TestCase):
    def test_request_audit_params_redacts_sensitive_values(self) -> None:
        request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.INVESTIGATING,
            tool_name="xdr_lookup",
            action_name="query",
            params={"token": "secret-token", "asset": "web-server-01"},
            reason="测试脱敏",
            idempotency_key="tool-contract-redact",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            sensitive_param_keys=["token"],
        )

        self.assertEqual(request.audit_params(), {"token": "***", "asset": "web-server-01"})

    def test_fixed_sample_tool_result_contains_audit_fields(self) -> None:
        request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.INVESTIGATING,
            tool_name="evidence_lookup",
            action_name="query_related_evidence",
            params={"event_id": "evt-test"},
            reason="测试工具结果契约",
            idempotency_key="tool-contract-success",
            risk_level=ToolRiskLevel.LOW,
        )

        result = FixedSampleAdapter().run_tool(request)

        self.assertEqual(result.call_id, request.call_id)
        self.assertEqual(result.trace_id, request.trace_id)
        self.assertEqual(result.event_id, request.event_id)
        self.assertEqual(result.tool_name, request.tool_name)
        self.assertEqual(result.action_name, request.action_name)
        self.assertEqual(result.idempotency_key, request.idempotency_key)
        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(result.side_effect_type, ToolSideEffectType.READ_ONLY)
        self.assertFalse(result.external_side_effect)
        self.assertIn("evidence-http-001", result.evidence_refs)

    def test_unsupported_tool_returns_structured_error(self) -> None:
        request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.INVESTIGATING,
            tool_name="unknown_tool",
            action_name="unknown_action",
            params={},
            reason="测试未知工具",
            idempotency_key="tool-contract-failed",
            risk_level=ToolRiskLevel.LOW,
        )

        result = FixedSampleAdapter().run_tool(request)

        self.assertEqual(result.status, ToolCallStatus.FAILED)
        self.assertEqual(result.error_type, ToolErrorType.UNSUPPORTED_TOOL)
        self.assertTrue(result.retryable)
        self.assertFalse(result.external_side_effect)
        self.assertEqual(result.side_effect_type, ToolSideEffectType.NONE)

    def test_stateful_response_mock_persists_execution_status(self) -> None:
        adapter = FixedSampleAdapter()
        request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.EXECUTING,
            tool_name="stateful_response_mock",
            action_name="stateful_mock_containment",
            params={"event_id": "evt-test", "target": "web-server-01"},
            reason="测试有状态 Mock 执行记录",
            idempotency_key="stateful-mock-test",
            risk_level=ToolRiskLevel.HIGH,
        )

        execution_result = adapter.run_tool(request)
        verification_request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.VERIFYING,
            tool_name="response_verify",
            action_name="query_action_status",
            params={"idempotency_key": "stateful-mock-test"},
            reason="测试有状态 Mock 验证",
            idempotency_key="stateful-mock-test",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )
        verification_result = adapter.run_tool(verification_request)

        self.assertEqual(execution_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(adapter.query_action_status("stateful-mock-test"), "executed")
        self.assertEqual(verification_result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(verification_result.evidence_refs, ["fixed://actions/stateful-mock-test"])

    def test_verify_missing_action_returns_structured_non_success(self) -> None:
        request = ToolRequest(
            trace_id="trace-test",
            event_id="evt-test",
            stage=BusinessStatus.VERIFYING,
            tool_name="response_verify",
            action_name="query_action_status",
            params={"idempotency_key": "missing-action"},
            reason="测试未找到处置记录",
            idempotency_key="missing-action",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )

        result = FixedSampleAdapter().run_tool(request)

        self.assertEqual(result.status, ToolCallStatus.PARTIAL_SUCCESS)
        self.assertEqual(result.error_type, ToolErrorType.PLATFORM_ERROR)
        self.assertTrue(result.retryable)
        self.assertEqual(result.output_preview["action_status"], "not_found")


if __name__ == "__main__":
    unittest.main()
