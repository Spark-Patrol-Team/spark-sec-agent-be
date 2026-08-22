from __future__ import annotations

from datetime import datetime, timezone

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)


class FixedSampleAdapter:
    """固定样例适配器，真实 XDR/MCP 参数确认前只用于可重复演示。"""

    def __init__(self) -> None:
        self._actions: dict[str, str] = {}

    def fetch_alerts(self, sample_id: str | None = None, xdr_event_id: str | None = None) -> list[AlertRecord]:
        if sample_id not in (None, "webshell-001"):
            raise ValueError(f"未知固定样例: {sample_id}")

        occurred_at = datetime(2026, 8, 21, 9, 10, tzinfo=timezone.utc)
        return [
            AlertRecord(
                alert_id="xdr-alert-001",
                source="fixed_sample",
                occurred_at=occurred_at,
                name="WebShell 上传后通信告警",
                alert_type="webshell",
                raw_severity="high",
                src_ip="10.10.2.15",
                dst_ip="172.16.8.21",
                src_port=52344,
                dst_port=80,
                assets=["web-server-01"],
                attack_status="suspicious",
                scenario_fields={
                    "http_path": "/upload/shell.jsp",
                    "process": "java",
                    "file_path": "/opt/app/upload/shell.jsp",
                },
                evidence_refs=[
                    EvidenceRef(
                        ref_id="evidence-http-001",
                        source="fixed_sample",
                        kind="http",
                        summary="上传路径出现 jsp 文件且随后发生可疑访问",
                    )
                ],
                raw_record_ref="fixed://webshell-001/raw/xdr-alert-001",
            ),
            AlertRecord(
                alert_id="xdr-alert-002",
                source="fixed_sample",
                occurred_at=occurred_at,
                name="疑似 WebShell 命令执行",
                alert_type="webshell",
                raw_severity="high",
                src_ip="10.10.2.15",
                dst_ip="172.16.8.21",
                src_port=52346,
                dst_port=80,
                assets=["web-server-01"],
                attack_status="suspicious",
                scenario_fields={
                    "http_path": "/upload/shell.jsp?cmd=id",
                    "process": "sh",
                    "file_path": "/opt/app/upload/shell.jsp",
                },
                evidence_refs=[
                    EvidenceRef(
                        ref_id="evidence-proc-001",
                        source="fixed_sample",
                        kind="process",
                        summary="Web 进程派生 shell 进程",
                    )
                ],
                raw_record_ref="fixed://webshell-001/raw/xdr-alert-002",
            ),
        ]

    def run_tool(self, request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        raw_result_ref = f"fixed://tools/{request.tool_name}/{request.call_id}"
        if request.tool_name == "evidence_lookup":
            summary = "已查询固定样例证据，确认上传文件、HTTP 访问和进程链存在关联"
            status = ToolCallStatus.SUCCESS
            evidence_refs = ["evidence-http-001", "evidence-proc-001"]
            output_preview = {"matched_evidence_count": 2}
            external_side_effect = False
            side_effect_type = ToolSideEffectType.READ_ONLY
            error_type = None
        elif request.tool_name == "stateful_response_mock":
            self._actions[request.idempotency_key] = "executed"
            summary = "有状态 Mock 处置已记录"
            status = ToolCallStatus.SUCCESS
            evidence_refs = []
            output_preview = {"action_status": "executed"}
            external_side_effect = True
            side_effect_type = ToolSideEffectType.STATE_CHANGE
            error_type = None
        elif request.tool_name == "response_verify":
            summary = "验证固定样例 Mock 处置状态为已执行"
            status = ToolCallStatus.SUCCESS
            evidence_refs = [f"fixed://actions/{request.idempotency_key}"]
            output_preview = {"action_status": self.query_action_status(request.idempotency_key)}
            external_side_effect = False
            side_effect_type = ToolSideEffectType.READ_ONLY
            error_type = None
        else:
            summary = f"固定样例暂不支持工具: {request.tool_name}"
            status = ToolCallStatus.FAILED
            evidence_refs = []
            output_preview = {}
            external_side_effect = False
            side_effect_type = ToolSideEffectType.NONE
            error_type = ToolErrorType.UNSUPPORTED_TOOL

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
            platform_status=status,
            external_side_effect=external_side_effect,
            side_effect_type=side_effect_type,
            attempt=request.attempt,
            max_attempts=request.max_attempts,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
        )

    def query_action_status(self, idempotency_key: str) -> str:
        return self._actions.get(idempotency_key, "not_found")
