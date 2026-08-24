from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)
from sec_agent.platforms.mock_state import StatefulMockLedger


SESSION_STATE: dict[str, dict[str, Any]] = {}


def build_stateful_response_handler(
    *,
    ledger: StatefulMockLedger,
    raw_result_prefix: str,
    action_ref_prefix: str,
    source_label: str,
) -> Callable[[ToolRequest], ToolResult]:
    def handle_stateful_response(request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        action_ref = f"{action_ref_prefix}/actions/{request.idempotency_key}"
        record = ledger.record_action(
            request.idempotency_key,
            action_status="executed",
            summary=f"{source_label} Mock 处置已记录",
            evidence_refs=[action_ref],
            output_preview={
                "action_status": "executed",
                "event_id": request.params.get("event_id"),
                "target": request.params.get("target"),
            },
        )
        raw_result_ref = f"{raw_result_prefix}/tools/{request.tool_name}/{request.call_id}"
        ended_at = utc_now()
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=ToolCallStatus.SUCCESS,
            summary=record.summary,
            raw_result_ref=raw_result_ref,
            evidence_refs=[],
            output_refs=[raw_result_ref],
            output_preview=dict(record.output_preview),
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

    return handle_stateful_response


def build_response_verify_handler(
    *,
    ledger: StatefulMockLedger,
    raw_result_prefix: str,
    source_label: str,
) -> Callable[[ToolRequest], ToolResult]:
    def handle_response_verify(request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        record = ledger.get(request.idempotency_key)
        if record is None:
            status = ToolCallStatus.PARTIAL_SUCCESS
            summary = f"未找到{source_label} Mock 处置记录"
            evidence_refs: list[str] = []
            output_preview = {"action_status": "not_found"}
            error_type = ToolErrorType.PLATFORM_ERROR
        else:
            status = ToolCallStatus.SUCCESS if record.action_status == "executed" else ToolCallStatus.PARTIAL_SUCCESS
            summary = record.summary if record.action_status == "executed" else f"{source_label} Mock 处置状态异常"
            evidence_refs = list(record.evidence_refs)
            output_preview = dict(record.output_preview)
            output_preview.setdefault("action_status", record.action_status)
            error_type = None if status == ToolCallStatus.SUCCESS else ToolErrorType.PLATFORM_ERROR

        raw_result_ref = f"{raw_result_prefix}/tools/{request.tool_name}/{request.call_id}"
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
            evidence_refs=evidence_refs,
            output_refs=[raw_result_ref],
            output_preview=output_preview,
            retryable=status != ToolCallStatus.SUCCESS,
            error_type=error_type,
            error_message=None if status == ToolCallStatus.SUCCESS else summary,
            platform_status=status.value,
            external_side_effect=False,
            side_effect_type=ToolSideEffectType.READ_ONLY,
            attempt=request.attempt,
            max_attempts=request.max_attempts,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
        )

    return handle_response_verify


def handle_stateful_mock(request: ToolRequest) -> ToolResult:
    """旧版会话 Mock 工具，保留用于独立工具调试。"""
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
