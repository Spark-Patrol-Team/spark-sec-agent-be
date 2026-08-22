from typing import Dict, Callable

from sec_agent.domain.models import ToolRequest, ToolResult
from sec_agent.tools.xdr_query_tool import handle_xdr_query
from sec_agent.tools.stateful_mock_tool import handle_stateful_mock

# 工具名 -> 处理函数映射
TOOL_HANDLER_MAP: Dict[str, Callable[[ToolRequest], ToolResult]] = {
    "xdr_log_query": handle_xdr_query,
    "stateful_mock": handle_stateful_mock,
}


def dispatch_tool(request: ToolRequest) -> ToolResult:
    """
    MVP工具调度入口
    只支持两个工具：xdr_log_query、stateful_mock
    其他tool_name直接返回错误ToolResult
    """
    handler = TOOL_HANDLER_MAP.get(request.tool_name)
    if handler is None:
        # 不支持的工具，组装错误返回，复用原有ToolResult结构
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            success=False,
            error_message=f"[MVP]不支持该工具:{request.tool_name},仅支持xdr_log_query / stateful_mock",
            data=None
        )
    # 执行对应工具逻辑
    return handler(request)
