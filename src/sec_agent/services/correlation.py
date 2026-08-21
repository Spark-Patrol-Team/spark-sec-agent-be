from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from sec_agent.domain.models import AlertRecord, SecurityEvent


class AlertCorrelationService:
    def correlate(self, alerts: list[AlertRecord]) -> SecurityEvent:
        if not alerts:
            raise ValueError("无法关联空告警列表")

        entities: dict[str, set[str]] = defaultdict(set)
        for alert in alerts:
            if alert.src_ip:
                entities["src_ips"].add(alert.src_ip)
            if alert.dst_ip:
                entities["dst_ips"].add(alert.dst_ip)
            for asset in alert.assets:
                entities["assets"].add(asset)

        first_seen = min(alert.occurred_at for alert in alerts)
        last_seen = max(alert.occurred_at for alert in alerts)
        alert_types = sorted({alert.alert_type for alert in alerts})
        asset_names = sorted(entities.get("assets", set()))

        return SecurityEvent(
            event_id=f"evt-{uuid4()}",
            alert_refs=[alert.alert_id for alert in alerts],
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            entities={key: sorted(value) for key, value in entities.items()},
            correlation_reason="按相同攻击类型、时间窗口和关键实体进行最小关联",
            alert_count_before=len(alerts),
            event_count_after=1,
            summary=f"{len(alerts)} 条 {','.join(alert_types)} 告警关联为 1 个事件，涉及资产 {','.join(asset_names)}",
        )

