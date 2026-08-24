from typing import Callable, Dict

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)
from sec_agent.tools.stateful_mock_tool import handle_stateful_mock
from sec_agent.tools.xdr_query_tool import handle_xdr_query

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
        started_at = utc_now()
        error_message = (
            f"[MVP]不支持该工具:{request.tool_name},"
            "仅支持xdr_log_query / stateful_mock"
        )
        ended_at = utc_now()
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=ToolCallStatus.FAILED,
            summary=error_message,
            output_preview={},
            retryable=False,
            error_type=ToolErrorType.UNSUPPORTED_TOOL,
            error_message=error_message,
            platform_status=ToolCallStatus.FAILED.value,
            external_side_effect=False,
            side_effect_type=ToolSideEffectType.NONE,
            attempt=request.attempt,
            max_attempts=request.max_attempts,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
        )
    # 执行对应工具逻辑
    return handler(request)
