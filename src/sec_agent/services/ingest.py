from __future__ import annotations

from sec_agent.domain.models import AlertRecord
from sec_agent.platforms.base import PlatformAdapter


class AlertIngestService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def ingest(self, source: str, sample_id: str | None, xdr_event_id: str | None) -> list[AlertRecord]:
        if source == "xdr":
            raise NotImplementedError("XDR OpenAPI 路径、鉴权和字段映射尚未确认")
        return self._platform.fetch_alerts(sample_id=sample_id, xdr_event_id=xdr_event_id)

