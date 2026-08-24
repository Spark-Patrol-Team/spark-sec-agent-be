from collections.abc import Callable

from sec_agent.domain.models import (
    ToolCallStatus,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)


EvidenceResolver = Callable[[ToolRequest], list[str]]


def build_evidence_lookup_handler(
    *,
    evidence_resolver: EvidenceResolver,
    raw_result_prefix: str,
    source_label: str,
) -> Callable[[ToolRequest], ToolResult]:
    def handle_evidence_lookup(request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        evidence_refs = evidence_resolver(request)
        raw_result_ref = f"{raw_result_prefix}/{request.tool_name}/{request.call_id}"
        ended_at = utc_now()
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=ToolCallStatus.SUCCESS,
            summary=f"已从 {source_label} 查询到 {len(evidence_refs)} 条证据引用",
            raw_result_ref=raw_result_ref,
            evidence_refs=evidence_refs,
            output_refs=[raw_result_ref],
            output_preview={
                "matched_alert_count": len(request.params.get("alert_refs", [])),
                "matched_evidence_count": len(evidence_refs),
            },
            retryable=False,
            error_type=None,
            error_message=None,
            platform_status=ToolCallStatus.SUCCESS.value,
            external_side_effect=False,
            side_effect_type=ToolSideEffectType.READ_ONLY,
            attempt=request.attempt,
            max_attempts=request.max_attempts,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
        )

    return handle_evidence_lookup


def handle_xdr_query(request: ToolRequest) -> ToolResult:
    """
    MVP XDR原始日志查询工具
    依据平台定向验证统一结论，只返回已经验证通过的字段
    MVP：优先使用本地内置样例，暂不强依赖真实XDR OpenAPI接口
    """
    started_at = utc_now()

    # ========== MVP 演示：内置样例数据，后续可以对接仓库里的样例json文件 ==========
    mock_xdr_records = [
        {
            "event_time": "2026-08-20T10:22:30Z",
            "rule_name": "STA-SQL注入攻击",
            "risk_level": "high",
            "src_ip": "192.168.1.100",
            "dst_ip": "10.0.0.5",
            "src_port": 54321,
            "dst_port": 8080,
            "origin_log": "HTTP请求携带SQL注入payload",
            "asset_info": "web-server-01"
        }
    ]

    raw_result_ref = f"builtin://xdr-log-query/{request.call_id}"
    ended_at = utc_now()
    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        idempotency_key=request.idempotency_key,
        status=ToolCallStatus.SUCCESS,
        summary=f"已返回{len(mock_xdr_records)}条内置XDR样例日志",
        raw_result_ref=raw_result_ref,
        output_refs=[raw_result_ref],
        output_preview={"records": mock_xdr_records},
        retryable=False,
        error_type=None,
        error_message=None,
        platform_status=ToolCallStatus.SUCCESS.value,
        external_side_effect=False,
        side_effect_type=ToolSideEffectType.READ_ONLY,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
    )
