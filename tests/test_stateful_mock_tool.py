import unittest

from sec_agent.domain.models import BusinessStatus, ToolCallStatus, ToolErrorType, ToolRequest, ToolRiskLevel
from sec_agent.tools.stateful_mock_tool import IDEMPOTENCY_RESULTS, SESSION_STATE, handle_stateful_mock


class StatefulMockToolTest(unittest.TestCase):
    def setUp(self) -> None:
        SESSION_STATE.clear()
        IDEMPOTENCY_RESULTS.clear()

    def make_request(self, *, idempotency_key: str, params: dict) -> ToolRequest:
        return ToolRequest(
            trace_id="trace-mock",
            event_id="event-mock",
            stage=BusinessStatus.EXECUTING,
            tool_name="stateful_mock",
            action_name="mock_invoke",
            params=params,
            reason="测试通用有状态 Mock",
            idempotency_key=idempotency_key,
            risk_level=ToolRiskLevel.LOW,
        )

    def test_session_state_is_retained_and_isolated(self) -> None:
        first = handle_stateful_mock(
            self.make_request(
                idempotency_key="mock-001",
                params={"session_id": "session-a", "input_data": {"alert_count": 2}},
            )
        )
        second = handle_stateful_mock(
            self.make_request(
                idempotency_key="mock-002",
                params={"session_id": "session-a", "input_data": {"note": "追加状态"}},
            )
        )
        other = handle_stateful_mock(
            self.make_request(
                idempotency_key="mock-003",
                params={"session_id": "session-b", "input_data": {"alert_count": 1}},
            )
        )

        self.assertEqual(first.status, ToolCallStatus.SUCCESS)
        self.assertEqual(
            second.output_preview["current_session_state"],
            {"alert_count": 2, "note": "追加状态"},
        )
        self.assertEqual(other.output_preview["current_session_state"], {"alert_count": 1})

    def test_duplicate_idempotency_key_does_not_write_again(self) -> None:
        request = self.make_request(
            idempotency_key="mock-duplicate",
            params={"session_id": "session-a", "input_data": {"count": 1}},
        )
        first = handle_stateful_mock(request)
        duplicate = handle_stateful_mock(request)

        self.assertEqual(first.status, ToolCallStatus.SUCCESS)
        self.assertEqual(duplicate.status, ToolCallStatus.SUCCESS)
        self.assertEqual(duplicate.output_preview["current_session_state"], {"count": 1})
        self.assertEqual(SESSION_STATE["session-a"], {"count": 1})

    def test_invalid_input_returns_structured_validation_error(self) -> None:
        result = handle_stateful_mock(
            self.make_request(
                idempotency_key="mock-invalid",
                params={"session_id": "session-a", "input_data": ["invalid"]},
            )
        )

        self.assertEqual(result.status, ToolCallStatus.FAILED)
        self.assertEqual(result.error_type, ToolErrorType.VALIDATION)


if __name__ == "__main__":
    unittest.main()
