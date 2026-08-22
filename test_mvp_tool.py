from sec_agent.domain.models import ToolRequest
from sec_agent.tools.tool_dispatcher import dispatch_tool

# --------测试1：调用xdr_log_query查询工具--------
req1 = ToolRequest(
    trace_id="trace‑001",
    event_id="event‑001",
    tool_name="xdr_log_query",
    action_name="query_log",
    params={}
)
res1 = dispatch_tool(req1)
print("====XDR查询结果====")
print(res1.model_dump_json(indent=2))

# --------测试2：有状态Mock，第一次调用session_abc--------
req2 = ToolRequest(
    trace_id="trace‑002",
    event_id="event‑002",
    tool_name="stateful_mock",
    action_name="mock_invoke",
    params={
        "session_id": "session_abc",
        "input_data": {"alert_count": 2}
    }
)
res2 = dispatch_tool(req2)
print("\n====Mock第一次调用====")
print(res2.model_dump_json(indent=2))

# --------测试3：同一个session_id再次调用，验证状态保留--------
req3 = ToolRequest(
    trace_id="trace‑003",
    event_id="event‑003",
    tool_name="stateful_mock",
    action_name="mock_invoke",
    params={
        "session_id": "session_abc",
        "input_data": {"note": "新增一条告警"}
    }
)
res3 = dispatch_tool(req3)
print("\n====Mock第二次调用（同session，状态要合并）====")
print(res3.model_dump_json(indent=2))

# --------测试4：调用不存在的工具，测试错误分支--------
req4 = ToolRequest(
    trace_id="trace‑004",
    event_id="event‑004",
    tool_name="not_support_tool",
    action_name="xxx",
    params={}
)
res4 = dispatch_tool(req4)
print("\n====不支持工具错误返回====")
print(res4.model_dump_json(indent=2))
