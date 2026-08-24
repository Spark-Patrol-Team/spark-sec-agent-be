from typing import Any, Dict

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)

# 内存存储状态：key = session_id，value = 当前会话保存的状态数据
SESSION_STATE: Dict[str, Dict[str, Any]] = {}


def handle_stateful_mock(request: ToolRequest) -> ToolResult:
    """
    MVP有状态Mock工具
    session_id从params获取，不改动ToolRequest模型
    同session_id多次调用会保留会话状态；不同session互相隔离
    """
    started_at = utc_now()
    params = request.params
    session_id = params.get("session_id")
    if not session_id:
        error_message = "stateful_mock缺少params.session_id"
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
            error_type=ToolErrorType.VALIDATION,
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

    # 会话不存在就初始化空状态
    if session_id not in SESSION_STATE:
        SESSION_STATE[session_id] = {}

    current_state = SESSION_STATE[session_id]

    # ========== Mock业务逻辑 ==========
    input_data = params.get("input_data", {})
    # 把输入合并进会话状态，实现“记忆”
    current_state.update(input_data)
    # 写回内存
    SESSION_STATE[session_id] = current_state

    raw_result_ref = f"memory://sessions/{session_id}"
    ended_at = utc_now()
    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        idempotency_key=request.idempotency_key,
        status=ToolCallStatus.SUCCESS,
        summary=f"有状态Mock会话{session_id}已更新",
        raw_result_ref=raw_result_ref,
        output_refs=[raw_result_ref],
        output_preview={
            "session_id": session_id,
            "current_session_state": current_state,
        },
        retryable=False,
        error_type=None,
        error_message=None,
        platform_status=ToolCallStatus.SUCCESS.value,
        external_side_effect=True,
        side_effect_type=ToolSideEffectType.STATE_CHANGE,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
    )
