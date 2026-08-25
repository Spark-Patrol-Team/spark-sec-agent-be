from __future__ import annotations

from datetime import datetime, timezone

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    ToolRequest,
    ToolResult,
)
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.tools.base import ToolDispatcher
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


class FixedSampleAdapter:
    """固定样例适配器，真实 XDR/MCP 参数确认前只用于可重复演示。"""

    def __init__(self) -> None:
        self._ledger = StatefulMockLedger()
        self._dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=self._resolve_evidence_refs,
            ledger=self._ledger,
            raw_result_prefix="fixed:/",
            action_ref_prefix="fixed:/",
            source_label="固定样例",
        )

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
        return self._dispatcher.dispatch(request)

    def query_action_status(self, idempotency_key: str) -> str:
        return self._ledger.query_action_status(idempotency_key)

    def _resolve_evidence_refs(self, request: ToolRequest) -> list[str]:
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            alert_refs = []
        alerts = self.fetch_alerts()
        evidence_by_alert = {alert.alert_id: [ref.ref_id for ref in alert.evidence_refs] for alert in alerts}
        if not alert_refs:
            return [ref for refs in evidence_by_alert.values() for ref in refs]

        refs: list[str] = []
        for alert_ref in alert_refs:
            refs.extend(evidence_by_alert.get(str(alert_ref), []))
        return refs

    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        return self._dispatcher
