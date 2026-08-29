from __future__ import annotations

from sec_agent.domain.models import AlertRecord
from sec_agent.platforms.base import PlatformAdapter


class AlertIngestService:
    _SOURCE_BY_BACKEND = {
        "fixed_sample": "fixed_sample",
        "jsonl_sample": "jsonl_sample",
        "xdr_openapi": "xdr",
    }

    def __init__(self, platform: PlatformAdapter, platform_backend: str | None = None) -> None:
        self._platform = platform
        self._platform_backend = platform_backend

    def ingest(self, source: str, sample_id: str | None, xdr_event_id: str | None) -> list[AlertRecord]:
        self._validate_source(source)
        return self._platform.fetch_alerts(sample_id=sample_id, xdr_event_id=xdr_event_id)

    def _validate_source(self, source: str) -> None:
        if self._platform_backend is None:
            return
        expected_source = self._SOURCE_BY_BACKEND.get(self._platform_backend)
        if expected_source is None:
            raise ValueError(f"未知平台接入后端: {self._platform_backend}")
        if source != expected_source:
            raise ValueError(
                f"请求来源 {source} 与当前平台后端 {self._platform_backend} 不匹配，应使用 source={expected_source}"
            )
