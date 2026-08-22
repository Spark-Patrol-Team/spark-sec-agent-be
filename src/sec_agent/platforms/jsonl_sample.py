from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    NormalizedAlertRecord,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolSideEffectType,
    utc_now,
)


class JsonlAlertParseError(ValueError):
    """JSONL 告警样例解析失败。"""


class JsonlSampleAdapter:
    """读取标准化 JSONL 告警，并适配为主流程使用的 AlertRecord。"""

    def __init__(self, fixture_dir: str | Path) -> None:
        self._fixture_dir = self._resolve_fixture_dir(fixture_dir)
        self._normalized_file = self._fixture_dir / "normalized_alerts.jsonl"
        self._actions: dict[str, str] = {}
        self._normalized_cache: list[NormalizedAlertRecord] | None = None
        self._alert_index: dict[str, AlertRecord] | None = None

    def fetch_alerts(self, sample_id: str | None = None, xdr_event_id: str | None = None) -> list[AlertRecord]:
        lookup_id = self._resolve_lookup_id(sample_id, xdr_event_id)
        alert_index = self._load_alert_index()

        if lookup_id is not None:
            alert = alert_index.get(lookup_id)
            if alert is None:
                raise ValueError(f"JSONL 样例不存在: {lookup_id}")
            return [alert]

        return list(alert_index.values())

    def run_tool(self, request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        raw_result_ref = f"jsonl://tools/{request.tool_name}/{request.call_id}"
        if request.tool_name == "evidence_lookup":
            alert_refs = request.params.get("alert_refs", [])
            evidence_refs = self._collect_evidence_refs(alert_refs)
            matched_count = len(evidence_refs)
            summary = f"已从 JSONL 样例中查询到 {matched_count} 条证据引用"
            status = ToolCallStatus.SUCCESS
            output_preview: dict[str, Any] = {
                "matched_alert_count": len(alert_refs),
                "matched_evidence_count": matched_count,
            }
            external_side_effect = False
            side_effect_type = ToolSideEffectType.READ_ONLY
            error_type = None
        elif request.tool_name == "stateful_response_mock":
            self._actions[request.idempotency_key] = "executed"
            summary = "JSONL 主链 Mock 处置已记录"
            status = ToolCallStatus.SUCCESS
            evidence_refs = []
            output_preview = {"action_status": "executed"}
            external_side_effect = True
            side_effect_type = ToolSideEffectType.STATE_CHANGE
            error_type = None
        elif request.tool_name == "response_verify":
            action_status = self.query_action_status(request.idempotency_key)
            if action_status == "executed":
                summary = "已验证 JSONL 主链 Mock 处置状态"
                status = ToolCallStatus.SUCCESS
                evidence_refs = [f"jsonl://actions/{request.idempotency_key}"]
                error_type = None
            else:
                summary = "未找到 JSONL 主链 Mock 处置记录"
                status = ToolCallStatus.PARTIAL_SUCCESS
                evidence_refs = []
                error_type = ToolErrorType.PLATFORM_ERROR
            output_preview = {"action_status": action_status}
            external_side_effect = False
            side_effect_type = ToolSideEffectType.READ_ONLY
        else:
            summary = f"JSONL 样例暂不支持工具: {request.tool_name}"
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

    def _load_normalized_records(self) -> list[NormalizedAlertRecord]:
        if self._normalized_cache is not None:
            return self._normalized_cache

        if not self._normalized_file.exists():
            raise FileNotFoundError(f"JSONL 标准化告警文件不存在: {self._normalized_file}")

        records: list[NormalizedAlertRecord] = []
        seen_event_ids: set[str] = set()
        for line_no, raw_line in enumerate(self._normalized_file.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                record = NormalizedAlertRecord.model_validate(payload)
            except json.JSONDecodeError as exc:
                raise JsonlAlertParseError(f"{self._normalized_file}:{line_no} 不是合法 JSON: {exc.msg}") from exc
            except ValidationError as exc:
                raise JsonlAlertParseError(
                    f"{self._normalized_file}:{line_no} 不符合标准化告警契约: {exc.errors()}"
                ) from exc

            if record.event_id in seen_event_ids:
                raise JsonlAlertParseError(f"{self._normalized_file}:{line_no} event_id 重复: {record.event_id}")
            seen_event_ids.add(record.event_id)
            records.append(record)

        if not records:
            raise JsonlAlertParseError(f"JSONL 标准化告警文件为空: {self._normalized_file}")
        self._normalized_cache = records
        return records

    def _load_alert_index(self) -> dict[str, AlertRecord]:
        if self._alert_index is None:
            self._alert_index = {
                record.event_id: self._to_alert_record(record) for record in self._load_normalized_records()
            }
        return self._alert_index

    def _to_alert_record(self, record: NormalizedAlertRecord) -> AlertRecord:
        scenario_fields = {
            "source_device_type": record.source_device_type,
            "source_device_name": record.source_device_name,
            "transport_protocol": record.transport_protocol,
            "application_protocol": record.application_protocol,
            "affected_asset": record.affected_asset,
            "evidence_source": record.evidence_source,
            "sample_nature": record.sample_nature,
            "risk_score_seed": record.risk_score_seed,
            "investigation_hint": record.investigation_hint,
            "recommended_action": record.recommended_action,
        }
        return AlertRecord(
            alert_id=record.event_id,
            source="jsonl_sample",
            occurred_at=record.event_time,
            name=record.rule_or_event_name,
            alert_type=record.event_type,
            raw_severity=record.severity,
            src_ip=record.source_ip,
            dst_ip=record.destination_ip,
            src_port=record.source_port,
            dst_port=record.destination_port,
            assets=[record.affected_asset] if record.affected_asset else [],
            attack_status=record.status,
            scenario_fields={key: value for key, value in scenario_fields.items() if value is not None},
            evidence_refs=[
                EvidenceRef(
                    ref_id=f"{record.event_id}:{field_name}",
                    source=record.evidence_source,
                    kind="normalized_field",
                    summary=f"标准化字段引用: {field_name}",
                )
                for field_name in record.evidence_refs
            ],
            raw_record_ref=f"jsonl://fixed_alerts/normalized_alerts.jsonl#{record.event_id}",
        )

    def _collect_evidence_refs(self, alert_refs: list[str]) -> list[str]:
        alert_index = self._load_alert_index()
        refs: list[str] = []
        for alert_ref in alert_refs:
            alert = alert_index.get(alert_ref)
            if alert is None:
                continue
            refs.extend(ref.ref_id for ref in alert.evidence_refs)
        return refs

    def _resolve_lookup_id(self, sample_id: str | None, xdr_event_id: str | None) -> str | None:
        if sample_id and xdr_event_id and sample_id != xdr_event_id:
            raise ValueError("sample_id 与 xdr_event_id 同时传入时必须一致")
        return sample_id or xdr_event_id

    def _resolve_fixture_dir(self, fixture_dir: str | Path) -> Path:
        path = Path(fixture_dir)
        if path.is_absolute() and path.exists():
            return path
        if path.exists():
            return path

        project_root = Path(__file__).resolve().parents[3]
        project_path = project_root / path
        if project_path.exists():
            return project_path
        return path
