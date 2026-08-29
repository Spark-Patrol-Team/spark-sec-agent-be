from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from sec_agent.domain.models import NormalizedAlertRecord


class RawAlertNormalizationError(ValueError):
    """原始 STA/XDR JSONL 无法标准化为统一告警时抛出。"""


class RawJsonlNormalizer:
    """将脱敏 STA/XDR 原始 JSONL 映射为 ``NormalizedAlertRecord``。

    规则以 ``tests/fixtures/fixed_alerts/raw_to_normalized_mapping.csv`` 为基线：
    WebShell 高危固定样例专项升级为 ``critical/95``；受影响资产优先使用
    ``destination_ip``，仅在目的地址缺失时回退 ``host_ip``。
    """

    _SHANGHAI = ZoneInfo("Asia/Shanghai")
    _STA_EVIDENCE_FIELDS = (
        "record_time",
        "rule_name",
        "reporting_device",
        "source_ip",
        "source_port",
        "destination_ip",
        "destination_port",
    )
    _XDR_EVIDENCE_FIELDS = (
        "alert_time",
        "alert_name",
        "alert_grade",
        "alert_classification",
        "source_ip",
        "destination_ip",
        "host_ip",
    )

    def load_jsonl(self, path: str | Path) -> list[NormalizedAlertRecord]:
        raw_file = Path(path)
        if not raw_file.exists():
            raise FileNotFoundError(f"原始 JSONL 告警文件不存在: {raw_file}")

        records: list[NormalizedAlertRecord] = []
        seen_event_ids: set[str] = set()
        for line_no, line in enumerate(raw_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw_record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RawAlertNormalizationError(f"{raw_file}:{line_no} 不是合法 JSON: {exc.msg}") from exc
            if not isinstance(raw_record, dict):
                raise RawAlertNormalizationError(f"{raw_file}:{line_no} 必须为 JSON 对象")
            try:
                record = self.normalize(raw_record)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise RawAlertNormalizationError(f"{raw_file}:{line_no} 标准化失败: {exc}") from exc
            if record.event_id in seen_event_ids:
                raise RawAlertNormalizationError(f"{raw_file}:{line_no} event_id 重复: {record.event_id}")
            seen_event_ids.add(record.event_id)
            records.append(record)

        if not records:
            raise RawAlertNormalizationError(f"原始 JSONL 告警文件为空: {raw_file}")
        return records

    def normalize(self, raw: Mapping[str, Any]) -> NormalizedAlertRecord:
        event_id = self._required_text(raw, "sample_id")
        sample_nature = self._sample_nature(raw)
        if self._is_xdr_alert(raw):
            return self._normalize_xdr(raw, event_id, sample_nature)
        return self._normalize_sta(raw, event_id, sample_nature)

    def _normalize_sta(
        self,
        raw: Mapping[str, Any],
        event_id: str,
        sample_nature: str,
    ) -> NormalizedAlertRecord:
        rule_name = self._required_text(raw, "rule_name")
        destination_ip = self._optional_text(raw, "destination_ip")
        return NormalizedAlertRecord(
            event_id=event_id,
            event_time=self._parse_time(self._required_text(raw, "record_time")),
            source_device_type="STA",
            source_device_name=(
                self._optional_text(raw, "reporting_device_name")
                or self._optional_text(raw, "reporting_device")
                or "STA"
            ),
            event_type=self._event_type(rule_name),
            rule_or_event_name=rule_name,
            severity=self._sta_severity(rule_name),
            source_ip=self._optional_text(raw, "source_ip"),
            source_port=self._optional_port(raw, "source_port"),
            destination_ip=destination_ip,
            destination_port=self._optional_port(raw, "destination_port"),
            transport_protocol="tcp" if self._optional_port(raw, "source_port") is not None else None,
            application_protocol=self._application_protocol(rule_name),
            affected_asset=destination_ip,
            evidence_source=self._evidence_source(raw, default="xdr_network_security_log"),
            evidence_refs=[field for field in self._STA_EVIDENCE_FIELDS if field in raw],
            sample_nature=sample_nature,
            status="new",
            risk_score_seed=self._risk_seed(self._sta_severity(rule_name)),
            investigation_hint=self._investigation_hint(self._event_type(rule_name)),
            recommended_action=self._recommended_action(self._event_type(rule_name)),
        )

    def _normalize_xdr(
        self,
        raw: Mapping[str, Any],
        event_id: str,
        sample_nature: str,
    ) -> NormalizedAlertRecord:
        alert_name = self._required_text(raw, "alert_name")
        alert_grade = self._optional_text(raw, "alert_grade") or "中危"
        destination_ip = self._optional_text(raw, "destination_ip") or self._optional_text(raw, "host_ip")
        severity, risk_score_seed = self._xdr_severity(alert_name, alert_grade)
        return NormalizedAlertRecord(
            event_id=event_id,
            event_time=self._parse_time(self._required_text(raw, "alert_time")),
            source_device_type="XDR",
            source_device_name=(
                self._optional_text(raw, "source_device_name")
                or self._optional_text(raw, "data_source")
                or "XDR"
            ),
            event_type=self._event_type(alert_name),
            rule_or_event_name=alert_name,
            severity=severity,
            source_ip=self._optional_text(raw, "source_ip"),
            source_port=self._optional_port(raw, "source_port"),
            destination_ip=destination_ip,
            destination_port=self._optional_port(raw, "destination_port"),
            transport_protocol="tcp" if self._optional_port(raw, "source_port") is not None else None,
            application_protocol=self._application_protocol(alert_name),
            affected_asset=destination_ip,
            evidence_source=self._evidence_source(raw, default="xdr_security_alert"),
            evidence_refs=[field for field in self._XDR_EVIDENCE_FIELDS if field in raw],
            sample_nature=sample_nature,
            status="new",
            risk_score_seed=risk_score_seed,
            investigation_hint=self._investigation_hint(self._event_type(alert_name)),
            recommended_action=self._recommended_action(self._event_type(alert_name)),
        )

    @staticmethod
    def _is_xdr_alert(raw: Mapping[str, Any]) -> bool:
        return "alert_time" in raw or raw.get("data_source") == "XDR"

    def _xdr_severity(self, alert_name: str, alert_grade: str) -> tuple[str, int]:
        if alert_name == "WebShell蚁剑工具文件管理" and alert_grade == "高危":
            return "critical", 95
        severity = {
            "严重": "critical",
            "高危": "high",
            "中危": "medium",
            "低危": "low",
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }.get(alert_grade.lower(), "medium")
        return severity, self._risk_seed(severity)

    @staticmethod
    def _sta_severity(rule_name: str) -> str:
        if "横向" in rule_name or "SMB" in rule_name.upper():
            return "medium"
        return "high"

    @staticmethod
    def _event_type(name: str) -> str:
        normalized = name.lower()
        if "sql" in normalized and "注入" in name:
            return "sql_injection"
        if "webshell" in normalized or "蚁剑" in name:
            return "webshell"
        if "横向" in name or "smb" in normalized:
            return "lateral_movement"
        if "未授权" in name:
            return "unauthorized_access"
        return "other"

    @staticmethod
    def _application_protocol(name: str) -> str | None:
        event_type = RawJsonlNormalizer._event_type(name)
        return {"sql_injection": "http", "webshell": "http", "lateral_movement": "smb"}.get(event_type)

    @staticmethod
    def _risk_seed(severity: str) -> int:
        return {"critical": 90, "high": 80, "medium": 65, "low": 30}[severity]

    @staticmethod
    def _investigation_hint(event_type: str) -> str:
        return {
            "sql_injection": "核查目标 Web 资产、同源 IP 历史访问、SQL 注入规则命中次数，以及是否存在后续 WebShell 行为。",
            "webshell": "核查受影响主机的文件变更、Web 访问日志、进程树和可疑连接，优先确认是否为真实 WebShell。",
            "lateral_movement": "核查源主机身份、SMB 共享访问、东西向连接基线和相邻资产中的同类访问。",
            "unauthorized_access": "核查认证日志、访问路径和受影响资源范围。",
        }.get(event_type, "核查原始证据、涉及资产与同源活动。")

    @staticmethod
    def _recommended_action(event_type: str) -> str:
        return {
            "sql_injection": "人工审批后限制源 IP 对目标 Web 服务的访问，并保留原始证据。",
            "webshell": "人工审批后隔离受影响主机或限制相关通信，并保留取证副本。",
            "lateral_movement": "人工审批后限制源主机到目标主机的 SMB 访问，并持续观察相邻资产。",
            "unauthorized_access": "人工审批后限制异常访问并保留认证与访问证据。",
        }.get(event_type, "保留证据并由人工确认后执行最小影响处置。")

    @staticmethod
    def _sample_nature(raw: Mapping[str, Any]) -> str:
        value = RawJsonlNormalizer._required_text(raw, "sample_nature")
        if value not in {"platform_derived", "synthetic_regression"}:
            raise ValueError(f"sample_nature 不合法: {value}")
        return value

    @staticmethod
    def _evidence_source(raw: Mapping[str, Any], default: str) -> str:
        sample_source = RawJsonlNormalizer._optional_text(raw, "sample_source")
        return {
            "XDR 日志检索": "xdr_network_security_log",
            "XDR 安全告警分析": "xdr_security_alert",
            "固定回归样例": "fixed_regression_fixture",
        }.get(sample_source, default)

    def _parse_time(self, value: Any) -> datetime:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=self._SHANGHAI)
        
        text = str(value).strip()
        # 尝试解析 Unix 时间戳字符串
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=self._SHANGHAI)
            
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            
        if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
            return parsed.replace(tzinfo=self._SHANGHAI)
        return parsed

    @staticmethod
    def _required_text(raw: Mapping[str, Any], key: str) -> str:
        value = RawJsonlNormalizer._optional_text(raw, key)
        if value is None:
            raise ValueError(f"缺少必填字段: {key}")
        return value

    @staticmethod
    def _optional_text(raw: Mapping[str, Any], key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_port(raw: Mapping[str, Any], key: str) -> int | None:
        value = raw.get(key)
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError(f"{key} 不能为布尔值")
        port = int(value)
        if not 0 <= port <= 65535:
            raise ValueError(f"{key} 超出端口范围: {port}")
        return port
