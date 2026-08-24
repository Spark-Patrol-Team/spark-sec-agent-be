from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from sec_agent.domain.models import AlertRecord, SecurityEvent


class AlertCorrelationService:
    """针对同一次主链输入执行最小告警压缩与实体汇总。

    调用方应将同一候选攻击活动（同场景、同目标资产、同来源设备且处于时间窗口内）
    的告警传入本服务。该服务不承担通用攻击图谱构建；它输出一个可供风险研判消费的
    ``SecurityEvent``，并保留压缩前后数量与关联依据。
    """

    def __init__(self, window_minutes: int = 15) -> None:
        if window_minutes <= 0:
            raise ValueError("关联时间窗口必须为正整数")
        self._window = timedelta(minutes=window_minutes)

    def correlate(self, alerts: list[AlertRecord]) -> SecurityEvent:
        if not alerts:
            raise ValueError("无法关联空告警列表")

        ordered_alerts = sorted(alerts, key=lambda alert: alert.occurred_at)
        self._validate_minimal_relation(ordered_alerts)
        entities: dict[str, set[str]] = defaultdict(set)
        source_devices: set[str] = set()
        for alert in ordered_alerts:
            if alert.src_ip:
                entities["src_ips"].add(alert.src_ip)
            if alert.dst_ip:
                entities["dst_ips"].add(alert.dst_ip)
            for asset in alert.assets:
                entities["assets"].add(asset)
            source_device = alert.scenario_fields.get("source_device_name")
            if isinstance(source_device, str) and source_device:
                source_devices.add(source_device)

        if source_devices:
            entities["source_devices"].update(source_devices)

        first_seen = ordered_alerts[0].occurred_at
        last_seen = ordered_alerts[-1].occurred_at
        alert_types = sorted({alert.alert_type for alert in ordered_alerts})
        asset_names = sorted(entities.get("assets", set()))
        source_names = sorted(entities.get("source_devices", set()))
        time_range = f"{first_seen.isoformat()} 至 {last_seen.isoformat()}"
        reason = (
            f"同一事件类型 {','.join(alert_types)}；"
            f"目标资产 {','.join(asset_names) or '未知'}；"
            f"来源设备 {','.join(source_names) or '未知'}；"
            f"时间窗口 {time_range}，不超过 {int(self._window.total_seconds() // 60)} 分钟"
        )

        return SecurityEvent(
            event_id=f"evt-{uuid4()}",
            alert_refs=[alert.alert_id for alert in ordered_alerts],
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            entities={key: sorted(value) for key, value in entities.items()},
            correlation_reason=reason,
            alert_count_before=len(ordered_alerts),
            event_count_after=1,
            summary=(
                f"已将 {len(ordered_alerts)} 条 {','.join(alert_types)} 告警压缩为 1 个安全事件；"
                f"涉及资产 {','.join(asset_names) or '未知'}。"
            ),
        )

    def _validate_minimal_relation(self, alerts: list[AlertRecord]) -> None:
        first = alerts[0]
        first_type = first.alert_type
        first_target = self._target_asset(first)
        first_device = self._source_device(first)
        for alert in alerts[1:]:
            if alert.alert_type != first_type:
                raise ValueError("告警事件类型不一致，应由上层拆分为多个安全事件")
            if self._target_asset(alert) != first_target:
                raise ValueError("告警目标资产不一致，应由上层拆分为多个安全事件")
            if self._source_device(alert) != first_device:
                raise ValueError("告警来源设备不一致，应由上层拆分为多个安全事件")
        if alerts[-1].occurred_at - alerts[0].occurred_at > self._window:
            raise ValueError("告警超出最小关联时间窗口，应由上层拆分为多个安全事件")

    @staticmethod
    def _target_asset(alert: AlertRecord) -> str | None:
        return alert.assets[0] if alert.assets else alert.dst_ip

    @staticmethod
    def _source_device(alert: AlertRecord) -> str | None:
        value = alert.scenario_fields.get("source_device_name")
        return value if isinstance(value, str) else None
