from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    NormalizedAlertRecord,
    ToolRequest,
    ToolResult,
)
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.platforms.raw_jsonl import RawJsonlNormalizer
from sec_agent.tools.base import ToolDispatcher
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


class JsonlAlertParseError(ValueError):
    """JSONL 告警样例解析失败。"""


class JsonlSampleAdapter:
    """读取标准化 JSONL 告警，并适配为主流程使用的 AlertRecord。"""

    def __init__(self, fixture_dir: str | Path, input_mode: str = "normalized") -> None:
        self._fixture_dir = self._resolve_fixture_dir(fixture_dir)
        if input_mode not in {"normalized", "raw"}:
            raise ValueError(f"不支持的 JSONL 输入模式: {input_mode}")
        self._input_mode = input_mode
        self._normalized_file = self._fixture_dir / "normalized_alerts.jsonl"
        self._ledger = StatefulMockLedger()
        self._dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=self._resolve_evidence_refs,
            ledger=self._ledger,
            raw_result_prefix="jsonl:/",
            action_ref_prefix="jsonl:/",
            source_label="JSONL 样例",
        )
        self._raw_file = self._fixture_dir / "raw_alerts.jsonl"
        self._normalizer = RawJsonlNormalizer()
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
        return self._dispatcher.dispatch(request)

    def query_action_status(self, idempotency_key: str) -> str:
        return self._ledger.query_action_status(idempotency_key)

    def _load_normalized_records(self) -> list[NormalizedAlertRecord]:
        if self._normalized_cache is not None:
            return self._normalized_cache

        if self._input_mode == "raw":
            try:
                self._normalized_cache = self._normalizer.load_jsonl(self._raw_file)
            except ValueError as exc:
                raise JsonlAlertParseError(str(exc)) from exc
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
            raw_record_ref=(
                f"jsonl://fixed_alerts/{'raw_alerts.jsonl' if self._input_mode == 'raw' else 'normalized_alerts.jsonl'}"
                f"#{record.event_id}"
            ),
        )

    def _resolve_evidence_refs(self, request: ToolRequest) -> list[str]:
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            return []
        alert_index = self._load_alert_index()
        refs: list[str] = []
        for alert_ref in alert_refs:
            alert = alert_index.get(str(alert_ref))
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

    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        return self._dispatcher
