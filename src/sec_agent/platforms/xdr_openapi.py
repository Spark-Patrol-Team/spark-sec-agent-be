from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import requests
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
from sec_agent.platforms.errors import PlatformIngestError
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.mock_state import StatefulMockLedger
from sec_agent.platforms.raw_jsonl import RawAlertNormalizationError, RawJsonlNormalizer
from sec_agent.tools.base import ToolDispatcher, ToolHandler
from sec_agent.tools.tool_dispatcher import build_platform_tool_dispatcher


@dataclass(frozen=True)
class XdrOpenApiConfig:
    base_url: str | None
    auth_type: str = "token"
    token: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    alerts_path: str = "/api/xdr/v1/alerts/list"
    logs_path: str = "/api/v1/logs"
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 30
    alert_page_size: int = 50
    alert_max_pages: int = 20
    alert_start_timestamp: int | None = None
    startup_check: bool = True
    preflight_http_check: bool = False
    allow_fixed_sample_fallback: bool = False


class XdrOpenApiAdapter:
    """XDR OpenAPI 真实平台接入边界。

    当前冻结后端主链需要的接口、配置和失败语义。告警列表按真实 XDR
    脱敏契约使用 POST 分页查询，按需在本地筛选告警唯一标识。
    """

    def __init__(
        self,
        config: XdrOpenApiConfig,
        *,
        session: requests.Session | None = None,
        fallback_adapter: FixedSampleAdapter | None = None,
        xdr_log_query_handler: ToolHandler | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._fallback_adapter = fallback_adapter
        self._fallback_alert_ids: set[str] = set()
        self._normalizer = RawJsonlNormalizer()
        self._ledger = StatefulMockLedger()
        self._dispatcher = build_platform_tool_dispatcher(
            evidence_resolver=self._resolve_evidence_refs,
            ledger=self._ledger,
            raw_result_prefix="xdr:/",
            action_ref_prefix="xdr:/",
            source_label="XDR OpenAPI",
            xdr_log_query_handler=xdr_log_query_handler or self._handle_xdr_log_query,
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
        if self._config.alert_page_size <= 0 or self._config.alert_max_pages <= 0:
            raise ValueError("XDR 告警分页大小和最大页数必须大于 0")

    def preflight_check(self) -> None:
        body = self._alert_list_body(page=1, page_size=1)
        try:
            response = self._session.post(
                self._endpoint(self._config.alerts_path),
                headers=self._headers("POST", self._config.alerts_path, body=body),
                json=body,
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
        if self._should_use_fallback_tools(request):
            return self._fallback_adapter.run_tool(request)
        return self._dispatcher.dispatch(request)

    def query_action_status(self, idempotency_key: str) -> str:
        return self._ledger.query_action_status(idempotency_key)

    def _fetch_real_alerts(self, lookup_id: str | None) -> list[AlertRecord]:
        records: list[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        page = 1
        total: int | None = None
        try:
            while page <= self._config.alert_max_pages:
                body = self._alert_list_body(page=page, page_size=self._config.alert_page_size)
                response = self._session.post(
                    self._endpoint(self._config.alerts_path),
                    headers=self._headers("POST", self._config.alerts_path, body=body),
                    json=body,
                    timeout=self._timeout(),
                )
                self._raise_for_alert_response(response)
                payload = self._json_payload(response)
                self._ensure_success_payload(payload, response.status_code)
                page_items = self._extract_items(payload)
                for item in page_items:
                    item_id = self._alert_lookup_key(item)
                    if lookup_id and item_id != lookup_id:
                        continue
                    dedupe_key = item_id or self._stringify_param(dict(item))
                    if dedupe_key in seen_ids:
                        continue
                    seen_ids.add(dedupe_key)
                    records.append(item)
                if lookup_id and records:
                    break
                total = self._extract_total(payload)
                if not self._should_fetch_next_page(page, len(page_items), total):
                    break
                page += 1
        except requests.Timeout as exc:
            raise PlatformIngestError(
                kind="timeout",
                message="XDR OpenAPI 请求超时",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
            ) from exc
        except requests.RequestException as exc:
            raise PlatformIngestError(
                kind="unreachable",
                message=f"XDR OpenAPI 不可达: {exc}",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
            ) from exc

        try:
            return [self._to_alert_record(item) for item in records]
        except (RawAlertNormalizationError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise PlatformIngestError(
                kind="field_mapping",
                message=f"XDR 字段转换失败: {exc}",
                retryable=False,
                allow_fallback=False,
                platform_status="200",
            ) from exc

    def _raise_for_alert_response(self, response: requests.Response) -> None:
        if response.status_code in {401, 403}:
            raise PlatformIngestError(
                kind="auth",
                message="XDR OpenAPI 鉴权失败",
                retryable=False,
                allow_fallback=False,
                platform_status=str(response.status_code),
            )
        if response.status_code >= 500:
            raise PlatformIngestError(
                kind="platform_error",
                message="XDR OpenAPI 返回服务端错误",
                retryable=True,
                allow_fallback=self._config.allow_fixed_sample_fallback,
                platform_status=str(response.status_code),
            )
        if response.status_code >= 400:
            raise PlatformIngestError(
                kind="platform_error",
                message="XDR OpenAPI 返回客户端错误",
                retryable=False,
                allow_fallback=False,
                platform_status=str(response.status_code),
            )

    def _json_payload(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformIngestError(
                kind="field_mapping",
                message="XDR OpenAPI 返回内容不是合法 JSON",
                retryable=False,
                allow_fallback=False,
                platform_status=str(response.status_code),
            ) from exc

    def _ensure_success_payload(self, payload: Any, status_code: int) -> None:
        if not isinstance(payload, Mapping) or "code" not in payload:
            return
        code = str(payload.get("code", "")).strip()
        if code in {"Success", "success", "0"}:
            return
        message = self._first_text(payload, "message", "msg") or f"业务状态异常: {code}"
        raise PlatformIngestError(
            kind="platform_error",
            message=f"XDR OpenAPI 返回业务错误: {message}",
            retryable=False,
            allow_fallback=False,
            platform_status=str(status_code),
        )

    def _extract_items(self, payload: Any) -> list[Mapping[str, Any]]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict) and "item" in data:
                items = data["item"]
            elif isinstance(data, dict) and "items" in data:
                items = data["items"]
            elif isinstance(data, list):
                items = data
            else:
                items = [data]
        else:
            raise ValueError("XDR 返回根节点必须为对象或数组")

        if not all(isinstance(item, Mapping) for item in items):
            raise ValueError("XDR 返回告警列表成员必须为对象")
        return list(items)

    def _extract_total(self, payload: Any) -> int | None:
        if not isinstance(payload, Mapping):
            return None
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return None
        total = data.get("total")
        if isinstance(total, bool) or total is None:
            return None
        try:
            return int(total)
        except (TypeError, ValueError):
            return None

    def _should_fetch_next_page(self, page: int, current_count: int, total: int | None) -> bool:
        if current_count <= 0:
            return False
        if page >= self._config.alert_max_pages:
            return False
        if total is None:
            return current_count >= self._config.alert_page_size
        return page * self._config.alert_page_size < total

    def _alert_list_body(self, page: int, page_size: int) -> dict[str, Any]:
        body: dict[str, Any] = {"page": page, "pageSize": page_size}
        if self._config.alert_start_timestamp is not None:
            body["startTimestamp"] = self._config.alert_start_timestamp
        return body

    def _to_alert_record(self, raw: Mapping[str, Any]) -> AlertRecord:
        try:
            normalized = NormalizedAlertRecord.model_validate(raw)
        except ValidationError:
            normalized = self._normalizer.normalize(self._to_normalizer_raw(raw))
        return self._from_normalized(normalized)

    def _to_normalizer_raw(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        event_id = self._first_text(raw, "event_id", "alert_id", "uuId", "uuid", "id", "sample_id")
        event_time = self._first_time_text(raw, "event_time", "alert_time", "occurred_at", "firstTime", "lastTime", "time", "created_at")
        alert_name = self._first_text(raw, "alert_name", "rule_name", "name", "title")
        if not event_id or not event_time or not alert_name:
            raise ValueError("缺少 event_id/alert_time/alert_name 等主链必需字段")
        return {
            "sample_id": event_id,
            "sample_nature": "platform_derived",
            "sample_source": "XDR 安全告警分析",
            "alert_time": event_time,
            "alert_name": alert_name,
            "alert_grade": self._first_text(raw, "alert_grade", "severity", "raw_severity", "level") or "中危",
            "alert_classification": self._first_text(raw, "alert_classification", "category", "type"),
            "source_ip": self._first_text(raw, "source_ip", "sourceIp", "src_ip", "srcIp", "src", "sourceIps", "srcIps"),
            "source_port": self._first_value(raw, "source_port", "sourcePort", "src_port", "srcPort", "sourcePorts", "srcPorts"),
            "destination_ip": self._first_text(
                raw,
                "destination_ip",
                "destinationIp",
                "dst_ip",
                "dstIp",
                "dst",
                "destIp",
                "destinationIps",
                "dstIps",
                "affected_asset",
            ),
            "destination_port": self._first_value(
                raw,
                "destination_port",
                "destinationPort",
                "dst_port",
                "dstPort",
                "destPort",
                "destinationPorts",
                "dstPorts",
            ),
            "host_ip": self._first_text(raw, "host_ip", "hostIp", "asset_ip", "assetIp"),
            "data_source": self._first_text(raw, "data_source") or "XDR",
            "source_device_name": self._first_text(raw, "source_device_name", "device_name") or "XDR",
        }

    def _from_normalized(self, record: NormalizedAlertRecord) -> AlertRecord:
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
        self._fallback_alert_ids.update(alert.alert_id for alert in alerts)
        fallback_alerts: list[AlertRecord] = []
        for alert in alerts:
            scenario_fields = dict(alert.scenario_fields)
            scenario_fields["platform_fallback"] = True
            scenario_fields["platform_fallback_source"] = "fixed_sample"
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

    def _should_use_fallback_tools(self, request: ToolRequest) -> bool:
        if self._fallback_adapter is None or not self._fallback_alert_ids:
            return False
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            return False
        return any(str(alert_ref) in self._fallback_alert_ids for alert_ref in alert_refs)

    def _resolve_evidence_refs(self, request: ToolRequest) -> list[str]:
        alert_refs = request.params.get("alert_refs", [])
        if not isinstance(alert_refs, list):
            return []
        return [f"xdr://evidence/{alert_ref}" for alert_ref in alert_refs]

    def _can_fallback(self, exc: PlatformIngestError) -> bool:
        return self._config.allow_fixed_sample_fallback and exc.allow_fallback

    def _handle_xdr_log_query(self, request: ToolRequest) -> ToolResult:
        started_at = utc_now()
        params = self._request_params(request.params)
        try:
            response = self._session.get(
                self._endpoint(self._config.logs_path),
                headers=self._headers("GET", self._config.logs_path, params),
                params=params,
                timeout=self._timeout(),
            )
            if response.status_code in {401, 403}:
                return self._tool_failed_result(request, started_at, "XDR 日志查询鉴权失败", "auth", response.status_code)
            if response.status_code >= 400:
                return self._tool_failed_result(
                    request,
                    started_at,
                    "XDR 日志查询平台返回错误",
                    "platform_error",
                    response.status_code,
                    retryable=response.status_code >= 500,
                )
            payload = response.json()
            records = self._extract_items(payload)
        except requests.Timeout:
            return self._tool_failed_result(request, started_at, "XDR 日志查询超时", "timeout", retryable=True)
        except requests.RequestException as exc:
            return self._tool_failed_result(request, started_at, f"XDR 日志查询不可达: {exc}", "platform_error", retryable=True)
        except (ValueError, TypeError) as exc:
            return self._tool_failed_result(request, started_at, f"XDR 日志查询返回转换失败: {exc}", "validation")

        raw_result_ref = f"xdr://openapi/logs/{request.call_id}"
        ended_at = utc_now()
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=ToolCallStatus.SUCCESS,
            summary=f"已从 XDR OpenAPI 查询到 {len(records)} 条日志",
            raw_result_ref=raw_result_ref,
            evidence_refs=[raw_result_ref],
            output_refs=[raw_result_ref],
            output_preview={"records": list(records)},
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

    def _tool_failed_result(
        self,
        request: ToolRequest,
        started_at: datetime,
        message: str,
        error_type: str,
        platform_status: int | None = None,
        retryable: bool = False,
    ) -> ToolResult:
        ended_at = utc_now()
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            status=ToolCallStatus.FAILED,
            summary=message,
            output_preview={},
            retryable=retryable,
            error_type=ToolErrorType(error_type),
            error_message=message,
            platform_status=str(platform_status) if platform_status is not None else ToolCallStatus.FAILED.value,
            external_side_effect=False,
            side_effect_type=ToolSideEffectType.READ_ONLY,
            attempt=request.attempt,
            max_attempts=request.max_attempts,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(1, int((ended_at - started_at).total_seconds() * 1000)),
        )

    def _endpoint(self, path: str) -> str:
        base_url = self._config.base_url or ""
        return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

    def _headers(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        if self._config.auth_type == "token":
            return {"Authorization": f"Bearer {self._config.token}"}
        return self._aksk_headers(method, path, params or {}, body or {})

    def _aksk_headers(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any],
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        canonical_path = urlsplit(path).path or "/"
        canonical_query = self._canonical_query(params)
        body_bytes = json.dumps(body or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        body_sha256 = hashlib.sha256(body_bytes).hexdigest()
        canonical = "\n".join(
            [
                method.upper(),
                canonical_path,
                canonical_query,
                timestamp,
                nonce,
                body_sha256,
            ]
        )
        digest = hmac.new(
            (self._config.secret_key or "").encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return {
            "X-XDR-Access-Key": self._config.access_key or "",
            "X-XDR-Timestamp": timestamp,
            "X-XDR-Nonce": nonce,
            "X-XDR-Signature-Method": "HMAC-SHA256",
            "X-XDR-Signature": base64.b64encode(digest).decode("ascii"),
        }

    def _canonical_query(self, params: Mapping[str, Any]) -> str:
        pairs = [(key, self._stringify_param(value)) for key, value in params.items() if value is not None]
        return "&".join(
            f"{quote(str(key), safe='')}={quote(value, safe='')}"
            for key, value in sorted(pairs)
        )

    @staticmethod
    def _request_params(params: Mapping[str, Any]) -> dict[str, str]:
        return {key: XdrOpenApiAdapter._stringify_param(value) for key, value in params.items() if value is not None}

    @staticmethod
    def _stringify_param(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _timeout(self) -> tuple[float, float]:
        return (self._config.connect_timeout_seconds, self._config.read_timeout_seconds)

    def _resolve_lookup_id(self, sample_id: str | None, xdr_event_id: str | None) -> str | None:
        if sample_id and xdr_event_id and sample_id != xdr_event_id:
            raise ValueError("sample_id 与 xdr_event_id 同时传入时必须一致")
        return xdr_event_id or sample_id

    def _alert_lookup_key(self, raw: Mapping[str, Any]) -> str | None:
        return self._first_text(raw, "event_id", "alert_id", "uuId", "uuid", "id", "sample_id")

    def _first_time_text(self, raw: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = self._first_value(raw, key)
            parsed = self._time_to_text(value)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _time_to_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).isoformat()
        text = str(value).strip()
        return text or None

    @staticmethod
    def _first_text(raw: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = XdrOpenApiAdapter._first_value(raw, key)
            if value is None:
                continue
            if isinstance(value, datetime):
                return value.isoformat()
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _first_value(raw: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, list | tuple):
                for item in value:
                    if item not in (None, ""):
                        return item
                continue
            if value not in (None, ""):
                return value
        return None

    @property
    def tool_dispatcher(self) -> ToolDispatcher:
        return self._dispatcher
