from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from pydantic import ValidationError

from sec_agent.domain.models import (
    AlertRecord,
    EvidenceRef,
    NormalizedAlertRecord,
    ToolRequest,
    ToolResult,
)
from sec_agent.platforms.errors import PlatformIngestError
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.platforms.raw_jsonl import RawAlertNormalizationError, RawJsonlNormalizer
from sec_agent.tools.base import ToolDispatcher
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


@dataclass(frozen=True)
class XdrOpenApiConfig:
    base_url: str | None
    auth_type: str = "token"
    token: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    alerts_path: str = "/api/xdr/v1/alerts/list"
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 30
    startup_check: bool = True
    preflight_http_check: bool = False
    allow_fixed_sample_fallback: bool = False


class XdrOpenApiAdapter:
    """XDR OpenAPI 真实平台接入边界。

    当前只冻结后端主链需要的接口、配置和失败语义；具体 OpenAPI 路径、
    HMAC 签名串和分页规则需在 28 日联调拿到实机记录后继续补齐。
    """

    def __init__(
        self,
        config: XdrOpenApiConfig,
        *,
        session: requests.Session | None = None,
        fallback_adapter: FixedSampleAdapter | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._fallback_adapter = fallback_adapter
        self._normalizer = RawJsonlNormalizer()
        self._ledger = StatefulMockLedger()
        self._dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=self._resolve_evidence_refs,
            ledger=self._ledger,
            raw_result_prefix="xdr:/",
            action_ref_prefix="xdr:/",
            source_label="XDR OpenAPI",
        )
        if config.startup_check:
            self.validate_startup_config()
        if config.preflight_http_check:
            self.preflight_check()

    def validate_startup_config(self) -> None:
        if not self._config.base_url:
            raise ValueError("启用 PLATFORM_BACKEND=xdr_openapi 时必须配置 XDR_BASE_URL")
        if self._config.auth_type == "token" and not self._config.token:
            raise ValueError("XDR_AUTH_TYPE=token 时必须配置 XDR_TOKEN")
        if self._config.auth_type == "aksk" and not (self._config.access_key and self._config.secret_key):
            raise ValueError("XDR_AUTH_TYPE=aksk 时必须配置 XDR_ACCESS_KEY 和 XDR_SECRET_KEY")
        if self._config.auth_type not in {"token", "aksk"}:
            raise ValueError(f"不支持的 XDR_AUTH_TYPE: {self._config.auth_type}")
        if self._config.connect_timeout_seconds <= 0 or self._config.read_timeout_seconds <= 0:
            raise ValueError("XDR 连接超时和读取超时必须大于 0")

    def preflight_check(self) -> None:
        try:
            response = self._session.get(
                self._endpoint(),
                headers=self._headers(),
                params={"limit": 1},
                timeout=self._timeout(),
            )
        except requests.Timeout as exc:
            raise PlatformIngestError(
                kind="timeout",
                message="XDR 启动前连通性检查超时",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
            ) from exc
        except requests.RequestException as exc:
            raise PlatformIngestError(
                kind="unreachable",
                message=f"XDR 启动前连通性检查不可达: {exc}",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
            ) from exc
        if response.status_code in {401, 403}:
            raise PlatformIngestError(
                kind="auth",
                message="XDR 启动前鉴权失败",
                retryable=False,
                allow_fallback=False,
                platform_status=str(response.status_code),
            )
        if response.status_code >= 500:
            raise PlatformIngestError(
                kind="platform_error",
                message="XDR 启动前平台返回服务端错误",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
                platform_status=str(response.status_code),
            )

    def fetch_alerts(self, sample_id: str | None = None, xdr_event_id: str | None = None) -> list[AlertRecord]:
        lookup_id = self._resolve_lookup_id(sample_id, xdr_event_id)
        try:
            alerts = self._fetch_real_alerts(lookup_id)
        except PlatformIngestError as exc:
            if self._can_fallback(exc):
                return self._fallback_alerts(lookup_id, str(exc))
            raise
        if not alerts:
            error = PlatformIngestError(
                kind="empty_result",
                message="XDR OpenAPI 返回空告警结果",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
            )
            if self._can_fallback(error):
                return self._fallback_alerts(lookup_id, str(error))
            raise error
        return alerts

    def run_tool(self, request: ToolRequest) -> ToolResult:
        return self._dispatcher.dispatch(request)

    def query_action_status(self, idempotency_key: str) -> str:
        return self._ledger.query_action_status(idempotency_key)

    def _fetch_real_alerts(self, lookup_id: str | None) -> list[AlertRecord]:
        # 已确认的真实接口是 POST + {page, pageSize}；保留旧 GET 形态以兼容已有联调夹具。
        is_real_list_api = self._config.alerts_path.rstrip("/") == "/api/xdr/v1/alerts/list"
        page = 1
        page_size = 10
        seen: dict[str, Mapping[str, Any]] = {}
        total: int | None = None
        while True:
            try:
                if is_real_list_api:
                    request = self._session.post
                    kwargs = {"json": {"page": page, "pageSize": page_size}}
                    if lookup_id:
                        kwargs["json"]["uuId"] = lookup_id
                else:
                    request = self._session.get
                    kwargs = {"params": {"event_id": lookup_id} if lookup_id else {"limit": 20}}
                response = request(self._endpoint(), headers=self._headers(), timeout=self._timeout(), **kwargs)
            except requests.Timeout as exc:
                raise PlatformIngestError(kind="timeout", message="XDR OpenAPI 请求超时", retryable=True,
                                           allow_fallback=self._config.allow_fixed_sample_fallback) from exc
            except requests.RequestException as exc:
                raise PlatformIngestError(kind="unreachable", message=f"XDR OpenAPI 不可达: {exc}", retryable=True,
                                           allow_fallback=self._config.allow_fixed_sample_fallback) from exc
            self._raise_for_status(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise PlatformIngestError(kind="field_mapping", message="XDR OpenAPI 返回内容不是合法 JSON",
                                           retryable=False, allow_fallback=False,
                                           platform_status=str(response.status_code)) from exc
            try:
                items, page_total, next_page = self._extract_page(payload)
                total = page_total if page_total is not None else total
                for item in items:
                    key = self._record_key(item)
                    if not key:
                        raise ValueError("真实 XDR 告警缺少可用于去重的稳定标识 uuId/event_id")
                    previous = seen.get(key)
                    if previous is None or self._record_completeness(item) >= self._record_completeness(previous):
                        seen[key] = item
                if not is_real_list_api or not items or next_page is False:
                    break
                if total is not None and len(seen) >= total:
                    break
                page += 1
                if page > 1000:
                    raise ValueError("XDR 分页超过安全上限")
            except (RawAlertNormalizationError, KeyError, TypeError, ValueError, ValidationError) as exc:
                raise PlatformIngestError(kind="field_mapping", message=f"XDR 字段转换失败: {exc}", retryable=False,
                                           allow_fallback=False, platform_status=str(response.status_code)) from exc
        try:
            return [self._to_alert_record(item) for item in seen.values()]
        except (RawAlertNormalizationError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise PlatformIngestError(kind="field_mapping", message=f"XDR 字段转换失败: {exc}", retryable=False,
                                       allow_fallback=False) from exc

    @staticmethod
    def _raise_for_status(response: Any) -> None:
        status = int(response.status_code)
        if status in {401, 403}:
            raise PlatformIngestError(kind="auth", message="XDR OpenAPI 鉴权失败", retryable=False,
                                       allow_fallback=False, platform_status=str(status))
        if status >= 500:
            raise PlatformIngestError(kind="platform_error", message="XDR OpenAPI 返回服务端错误", retryable=True,
                                       allow_fallback=True, platform_status=str(status))
        if status >= 400:
            raise PlatformIngestError(kind="platform_error", message="XDR OpenAPI 返回客户端错误", retryable=False,
                                       allow_fallback=False, platform_status=str(status))

    def _extract_page(self, payload: Any) -> tuple[list[Mapping[str, Any]], int | None, bool | None]:
        if isinstance(payload, list):
            raw_data: Any = payload
            meta: Mapping[str, Any] = {}
        elif isinstance(payload, Mapping):
            raw_data = payload.get("data", payload)
            meta = raw_data if isinstance(raw_data, Mapping) else payload
        else:
            raise ValueError("XDR 返回根节点必须为对象或数组")
        if isinstance(raw_data, Mapping):
            items = raw_data.get("item", raw_data.get("items", raw_data.get("records", [])))
            total = self._optional_int(raw_data.get("total"))
            current = self._optional_int(raw_data.get("page")) or 1
            size = self._optional_int(raw_data.get("pageSize")) or len(items) or 1
            has_more = (current * size < total) if total is not None else None
        else:
            items, total, has_more = raw_data, None, False
        if items is None:
            items = []
        if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
            raise ValueError("XDR 返回告警列表成员必须为对象")
        return list(items), total, has_more

    def _extract_items(self, payload: Any) -> list[Mapping[str, Any]]:
        return self._extract_page(payload)[0]

    @staticmethod
    def _record_key(raw: Mapping[str, Any]) -> str | None:
        for key in ("uuId", "uuid", "event_id", "alert_id", "id", "sample_id"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _record_completeness(raw: Mapping[str, Any]) -> int:
        return sum(value not in (None, "", [], {}) for value in raw.values())

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError("数值字段不能为布尔值")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"非法数值: {value}") from exc

    def _to_alert_record(self, raw: Mapping[str, Any]) -> AlertRecord:
        try:
            normalized = NormalizedAlertRecord.model_validate(raw)
        except ValidationError:
            normalized = self._normalizer.normalize(self._to_normalizer_raw(raw))
        return self._from_normalized(normalized)

    def _to_normalizer_raw(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        event_id = self._first_text(raw, "event_id", "alert_id", "id", "sample_id", "uuId", "uuid", "alertRuleId")
        event_time = self._first_text(raw, "event_time", "alert_time", "occurred_at", "time", "created_at")
        if event_time is None:
            event_time = self._epoch_to_iso(raw.get("firstTime") or raw.get("lastTime") or raw.get("updateTime"))
        alert_name = self._first_text(raw, "alert_name", "rule_name", "name", "title")
        if not event_id or not event_time or not alert_name:
            raise ValueError("缺少 event_id/alert_time/alert_name 等主链必需字段")
        source_ip = self._first_value(raw, "source_ip", "src_ip", "src", "srcIp")
        destination_ip = self._first_value(raw, "destination_ip", "dst_ip", "dst", "dstIp")
        host_ip = self._first_text(raw, "host_ip", "asset_ip", "hostIp")
        severity_value = raw.get("severity", raw.get("alert_grade", raw.get("raw_severity", raw.get("level"))))
        if isinstance(severity_value, (int, float)):
            severity_value = "严重" if severity_value >= 90 else "高危" if severity_value >= 70 else "中危" if severity_value >= 40 else "低危"
        classification = self._first_text(raw, "alert_classification", "category", "type", "threatSubTypeDesc", "threatTypeDesc", "threatClassDesc")
        return {
            "sample_id": event_id, "sample_nature": "platform_derived", "sample_source": "XDR 安全告警分析",
            "alert_time": event_time, "alert_name": alert_name, "alert_grade": severity_value or "中危",
            "alert_classification": classification, "source_ip": source_ip,
            "source_port": self._first_value(raw, "source_port", "src_port", "srcPort"),
            "destination_ip": destination_ip, "destination_port": self._first_value(raw, "destination_port", "dst_port", "dstPort"),
            "host_ip": host_ip, "data_source": self._first_value(raw, "data_source", "devSourceName", "devUidDesc") or "XDR",
            "source_device_name": self._first_value(raw, "source_device_name", "device_name", "devSourceName", "devUidDesc") or "XDR",
        }

    def _from_normalized(self, record: NormalizedAlertRecord) -> AlertRecord:
        scenario_fields = {
            "source_device_type": record.source_device_type, "source_device_name": record.source_device_name,
            "transport_protocol": record.transport_protocol, "application_protocol": record.application_protocol,
            "affected_asset": record.affected_asset, "evidence_source": record.evidence_source,
            "sample_nature": record.sample_nature, "risk_score_seed": record.risk_score_seed,
            "investigation_hint": record.investigation_hint, "recommended_action": record.recommended_action,
        }
        return AlertRecord(
            alert_id=record.event_id,
            source="xdr_openapi",
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
                    kind="xdr_field",
                    summary=f"XDR 字段引用: {field_name}",
                )
                for field_name in record.evidence_refs
            ],
            raw_record_ref=f"xdr://openapi/alerts#{record.event_id}",
        )

    def _fallback_alerts(self, lookup_id: str | None, reason: str) -> list[AlertRecord]:
        if self._fallback_adapter is None:
            raise PlatformIngestError(
                kind="fallback_unavailable",
                message="已允许降级但未配置固定样例 fallback 适配器",
                retryable=False,
                allow_fallback=False,
            )
        sample_id = lookup_id if lookup_id == "webshell-001" else "webshell-001"
        alerts = self._fallback_adapter.fetch_alerts(sample_id=sample_id)
        fallback_alerts: list[AlertRecord] = []
        for alert in alerts:
            scenario_fields = dict(alert.scenario_fields)
            scenario_fields["platform_fallback"] = True
            scenario_fields["platform_fallback_reason"] = reason
            fallback_alerts.append(
                alert.model_copy(
                    update={
                        "source": "fixed_sample_fallback",
                        "scenario_fields": scenario_fields,
                        "raw_record_ref": f"fallback+{alert.raw_record_ref}",
                    },
                    deep=True,
                )
            )
        return fallback_alerts

    def _resolve_evidence_refs(self, request: ToolRequest) -> list[str]:
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            return []
        return [f"xdr://evidence/{alert_ref}" for alert_ref in alert_refs]

    def _can_fallback(self, exc: PlatformIngestError) -> bool:
        return self._config.allow_fixed_sample_fallback and exc.allow_fallback

    def _endpoint(self) -> str:
        base_url = self._config.base_url or ""
        return urljoin(base_url.rstrip("/") + "/", self._config.alerts_path.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        if self._config.auth_type == "token":
            return {"Authorization": f"Bearer {self._config.token}"}
        # HMAC 签名串需按 28 日联调确认的 XDR 文档补齐；这里先只隔离敏感配置边界。
        return {"X-XDR-Access-Key": self._config.access_key or ""}

    def _timeout(self) -> tuple[float, float]:
        return (self._config.connect_timeout_seconds, self._config.read_timeout_seconds)

    def _resolve_lookup_id(self, sample_id: str | None, xdr_event_id: str | None) -> str | None:
        if sample_id and xdr_event_id and sample_id != xdr_event_id:
            raise ValueError("sample_id 与 xdr_event_id 同时传入时必须一致")
        return xdr_event_id or sample_id

    @staticmethod
    def _epoch_to_iso(value: Any) -> str | None:
        if value is None or value == "":
            return None
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=8))).isoformat()

    @staticmethod
    def _first_value(raw: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            if value is not None and str(value).strip():
                return value
        return None

    @staticmethod
    def _first_text(raw: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = raw.get(key)
            if value is None:
                continue
            if isinstance(value, datetime):
                return value.isoformat()
            text = str(value).strip()
            if text:
                return text
        return None

    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        return self._dispatcher
