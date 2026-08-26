from __future__ import annotations

import unittest

from sec_agent.domain.models import (
    BusinessStatus,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolRiskLevel,
)
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


class MvpToolDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=lambda request: [],
            ledger=StatefulMockLedger(),
            raw_result_prefix="test:/",
            action_ref_prefix="test:/",
            source_label="MVP测试平台",
        )

    def test_xdr_log_query_returns_builtin_sample(self) -> None:
        result = self.dispatcher.dispatch(
            self.make_request(
                trace_id="trace-001",
                event_id="event-001",
                tool_name="xdr_log_query",
                action_name="query_log",
                params={},
            )
        )

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(len(result.output_preview["records"]), 1)

    def test_stateful_mock_merges_session_state(self) -> None:
        first = self.dispatcher.dispatch(
            self.make_request(
                trace_id="trace-002",
                event_id="event-002",
                tool_name="stateful_mock",
                action_name="mock_invoke",
                params={"session_id": "session_abc", "input_data": {"alert_count": 2}},
            )
        )
        second = self.dispatcher.dispatch(
            self.make_request(
                trace_id="trace-003",
                event_id="event-003",
                tool_name="stateful_mock",
                action_name="mock_invoke",
                params={"session_id": "session_abc", "input_data": {"note": "新增一条告警"}},
            )
        )

        self.assertEqual(first.status, ToolCallStatus.SUCCESS)
        self.assertEqual(second.status, ToolCallStatus.SUCCESS)
        self.assertEqual(
            second.output_preview["current_session_state"],
            {
                "alert_count": 2,
                "note": "新增一条告警",
            },
        )

    def test_unknown_tool_returns_structured_error(self) -> None:
        result = self.dispatcher.dispatch(
            self.make_request(
                trace_id="trace-004",
                event_id="event-004",
                tool_name="not_support_tool",
                action_name="xxx",
                params={},
            )
        )

        self.assertEqual(result.status, ToolCallStatus.FAILED)
        self.assertEqual(result.error_type, ToolErrorType.UNSUPPORTED_TOOL)
        self.assertIn("不支持工具", result.error_message or "")

    def make_request(
        self,
        *,
        trace_id: str,
        event_id: str,
        tool_name: str,
        action_name: str,
        params: dict,
    ) -> ToolRequest:
        return ToolRequest(
            trace_id=trace_id,
            event_id=event_id,
            stage=BusinessStatus.INVESTIGATING,
            tool_name=tool_name,
            action_name=action_name,
            params=params,
            reason="验证 MVP 工具契约和返回结果",
            idempotency_key=f"{trace_id}:{tool_name}:{action_name}",
            risk_level=ToolRiskLevel.LOW,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
