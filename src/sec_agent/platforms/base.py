from __future__ import annotations

from typing import Protocol

from sec_agent.domain.models import AlertRecord, ToolRequest, ToolResult


class PlatformAdapter(Protocol):
    def fetch_alerts(self, sample_id: str | None = None, xdr_event_id: str | None = None) -> list[AlertRecord]:
        raise NotImplementedError

    def run_tool(self, request: ToolRequest) -> ToolResult:
        raise NotImplementedError

    def query_action_status(self, idempotency_key: str) -> str:
        raise NotImplementedError

