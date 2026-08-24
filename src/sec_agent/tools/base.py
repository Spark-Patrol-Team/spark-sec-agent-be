from __future__ import annotations

from collections.abc import Callable, Mapping

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)


ToolHandler = Callable[[ToolRequest], ToolResult]


class ToolDispatcher:
    """统一工具调度入口，负责把 ToolRequest 分发给已注册工具。"""

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = dict(handlers)

    def dispatch(self, request: ToolRequest) -> ToolResult:
        handler = self._handlers.get(request.tool_name)
        if handler is None:
            return unsupported_tool_result(request, sorted(self._handlers))
        return handler(request)


def unsupported_tool_result(request: ToolRequest, supported_tools: list[str]) -> ToolResult:
    started_at = utc_now()
    summary = f"不支持工具: {request.tool_name}；当前支持: {', '.join(supported_tools) or '无'}"
    ended_at = utc_now()
    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        idempotency_key=request.idempotency_key,
        status=ToolCallStatus.FAILED,
        summary=summary,
        output_preview={},
        retryable=True,
        error_type=ToolErrorType.UNSUPPORTED_TOOL,
        error_message=summary,
        platform_status=ToolCallStatus.FAILED.value,
        external_side_effect=False,
        side_effect_type=ToolSideEffectType.NONE,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
    )
