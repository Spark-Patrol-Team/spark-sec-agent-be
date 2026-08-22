from pathlib import Path
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sec_agent.domain.models import (  # noqa: E402
    BusinessStatus,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolRiskLevel,
)
from sec_agent.tool.tool_dispatcher import dispatch_tool  # noqa: E402


def make_request(
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
        reason="验证MVP工具契约和返回结果",
        idempotency_key=f"{trace_id}:{tool_name}:{action_name}",
        risk_level=ToolRiskLevel.LOW,
    )

# --------测试1：调用xdr_log_query查询工具--------
req1 = make_request(
    trace_id="trace-001",
    event_id="event-001",
    tool_name="xdr_log_query",
    action_name="query_log",
    params={},
)
res1 = dispatch_tool(req1)
print("====XDR查询结果====")
print(res1.model_dump_json(indent=2))
assert res1.status == ToolCallStatus.SUCCESS
assert len(res1.output_preview["records"]) == 1

# --------测试2：有状态Mock，第一次调用session_abc--------
req2 = make_request(
    trace_id="trace-002",
    event_id="event-002",
    tool_name="stateful_mock",
    action_name="mock_invoke",
    params={
        "session_id": "session_abc",
        "input_data": {"alert_count": 2}
    },
)
res2 = dispatch_tool(req2)
print("\n====Mock第一次调用====")
print(res2.model_dump_json(indent=2))
assert res2.status == ToolCallStatus.SUCCESS
assert res2.output_preview["current_session_state"] == {"alert_count": 2}

# --------测试3：同一个session_id再次调用，验证状态保留--------
req3 = make_request(
    trace_id="trace-003",
    event_id="event-003",
    tool_name="stateful_mock",
    action_name="mock_invoke",
    params={
        "session_id": "session_abc",
        "input_data": {"note": "新增一条告警"}
    },
)
res3 = dispatch_tool(req3)
print("\n====Mock第二次调用（同session，状态要合并）====")
print(res3.model_dump_json(indent=2))
assert res3.status == ToolCallStatus.SUCCESS
assert res3.output_preview["current_session_state"] == {
    "alert_count": 2,
    "note": "新增一条告警",
}

# --------测试4：调用不存在的工具，测试错误分支--------
req4 = make_request(
    trace_id="trace-004",
    event_id="event-004",
    tool_name="not_support_tool",
    action_name="xxx",
    params={},
)
res4 = dispatch_tool(req4)
print("\n====不支持工具错误返回====")
print(res4.model_dump_json(indent=2))
assert res4.status == ToolCallStatus.FAILED
assert res4.error_type == ToolErrorType.UNSUPPORTED_TOOL
assert "不支持该工具" in (res4.error_message or "")

print("\n====全部MVP工具验证通过====")
