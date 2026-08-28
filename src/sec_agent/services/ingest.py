from __future__ import annotations

from sec_agent.domain.models import AlertRecord
from sec_agent.platforms.base import PlatformAdapter


class AlertIngestService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def ingest(self, source: str, sample_id: str | None, xdr_event_id: str | None) -> list[AlertRecord]:
        return self._platform.fetch_alerts(sample_id=sample_id, xdr_event_id=xdr_event_id)
