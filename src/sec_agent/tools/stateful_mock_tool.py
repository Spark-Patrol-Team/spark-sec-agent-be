from copy import deepcopy
from typing import Any

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)

# 通用有状态工具的会话存储，与处置专用的 StatefulMockLedger 分开。
SESSION_STATE: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_RESULTS: dict[str, ToolResult] = {}


def _result(
    request: ToolRequest,
    *,
    status: ToolCallStatus,
    summary: str,
    output_preview: dict[str, Any],
    raw_result_ref: str | None = None,
    error_type: ToolErrorType | None = None,
    external_side_effect: bool = False,
    side_effect_type: ToolSideEffectType = ToolSideEffectType.NONE,
) -> ToolResult:
    started_at = utc_now()
    ended_at = utc_now()
    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        idempotency_key=request.idempotency_key,
        status=status,
        summary=summary,
        raw_result_ref=raw_result_ref,
        output_refs=[raw_result_ref] if raw_result_ref else [],
        output_preview=output_preview,
        retryable=False,
        error_type=error_type,
        error_message=None if error_type is None else summary,
        platform_status=status.value,
        external_side_effect=external_side_effect,
        side_effect_type=side_effect_type,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
    )


def get_session_state(session_id: str) -> dict[str, Any] | None:
    state = SESSION_STATE.get(session_id)
    return deepcopy(state) if state is not None else None


def handle_stateful_mock(request: ToolRequest) -> ToolResult:
    """
    通用有状态 Mock 工具。

    session_id 决定会话隔离范围，input_data 会合并进该会话状态；
    idempotency_key 防止同一个工具请求重复写入。
    """
    params = request.params
    session_id = params.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _result(
            request,
            status=ToolCallStatus.FAILED,
            summary="stateful_mock缺少有效的 params.session_id",
            output_preview={},
            error_type=ToolErrorType.VALIDATION,
        )

    cached_result = IDEMPOTENCY_RESULTS.get(request.idempotency_key)
    if cached_result is not None:
        return deepcopy(cached_result)

    input_data = params.get("input_data", {})
    if not isinstance(input_data, dict):
        return _result(
            request,
            status=ToolCallStatus.FAILED,
            summary="stateful_mock的 params.input_data 必须是对象",
            output_preview={},
            error_type=ToolErrorType.VALIDATION,
        )

    current_state = SESSION_STATE.setdefault(session_id, {})
    current_state.update(input_data)

    raw_result_ref = f"memory://sessions/{session_id}"
    result = _result(
        request,
        status=ToolCallStatus.SUCCESS,
        summary=f"有状态Mock会话{session_id}已更新",
        raw_result_ref=raw_result_ref,
        output_preview={
            "session_id": session_id,
            "current_session_state": deepcopy(current_state),
        },
        external_side_effect=True,
        side_effect_type=ToolSideEffectType.STATE_CHANGE,
    )
    IDEMPOTENCY_RESULTS[request.idempotency_key] = deepcopy(result)
    return result
