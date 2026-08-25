from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, Protocol

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)


class ResponseLedger(Protocol):
    """处置记录账本协议，避免工具层反向依赖具体平台适配器。"""

    def record_action(
        self,
        idempotency_key: str,
        *,
        action_status: str,
        summary: str,
        evidence_refs: list[str] | None = None,
        output_preview: dict[str, Any] | None = None,
    ) -> Any:
        raise NotImplementedError

    def get(self, idempotency_key: str) -> Any | None:
        raise NotImplementedError

    def query_action_status(self, idempotency_key: str) -> str:
        raise NotImplementedError


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
    """通用有状态 Mock 工具，用于开发期验证工具幂等与状态写入。"""
    params = request.params
    session_id = params.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return _result(
            request,
            status=ToolCallStatus.FAILED,
            summary="stateful_mock 缺少有效的 params.session_id",
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
            summary="stateful_mock 的 params.input_data 必须是对象",
            output_preview={},
            error_type=ToolErrorType.VALIDATION,
        )

    current_state = SESSION_STATE.setdefault(session_id, {})
    current_state.update(input_data)

    raw_result_ref = f"memory://sessions/{session_id}"
    result = _result(
        request,
        status=ToolCallStatus.SUCCESS,
        summary=f"有状态 Mock 会话 {session_id} 已更新",
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


def build_stateful_response_handler(
    *,
    ledger: ResponseLedger,
    raw_result_prefix: str,
    action_ref_prefix: str,
    source_label: str,
) -> Callable[[ToolRequest], ToolResult]:
    def handle_stateful_response(request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        raw_result_ref = f"{raw_result_prefix}/tools/{request.tool_name}/{request.call_id}"
        action_ref = _action_ref(action_ref_prefix, request.idempotency_key)
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


def _action_ref(action_ref_prefix: str, idempotency_key: str) -> str:
    prefix = action_ref_prefix.rstrip("/")
    if prefix.endswith("/actions"):
        return f"{prefix}/{idempotency_key}"
    return f"{action_ref_prefix}/actions/{idempotency_key}"


def build_response_verify_handler(
    *,
    ledger: ResponseLedger,
    raw_result_prefix: str,
    source_label: str,
) -> Callable[[ToolRequest], ToolResult]:
    def handle_response_verify(request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        raw_result_ref = f"{raw_result_prefix}/tools/{request.tool_name}/{request.call_id}"
        action_status = ledger.query_action_status(request.idempotency_key)
        if action_status == "executed":
            record = ledger.get(request.idempotency_key)
            status = ToolCallStatus.SUCCESS
            summary = f"已验证 {source_label} Mock 处置状态"
            evidence_refs = list(record.evidence_refs) if record is not None else []
            error_type = None
        else:
            status = ToolCallStatus.PARTIAL_SUCCESS
            summary = f"未找到 {source_label} Mock 处置记录"
            evidence_refs = []
            error_type = ToolErrorType.PLATFORM_ERROR

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
            output_preview={"action_status": action_status},
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
