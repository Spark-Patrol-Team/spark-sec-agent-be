from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sec_agent.domain.models import utc_now


@dataclass(slots=True)
class MockActionRecord:
    action_status: str
    summary: str
    evidence_refs: list[str] = field(default_factory=list)
    output_preview: dict[str, Any] = field(default_factory=dict)
    recorded_at: datetime = field(default_factory=utc_now)


class StatefulMockLedger:
    def __init__(self) -> None:
        self._records: dict[str, MockActionRecord] = {}

    def record_action(
        self,
        idempotency_key: str,
        *,
        action_status: str,
        summary: str,
        evidence_refs: list[str] | None = None,
        output_preview: dict[str, Any] | None = None,
    ) -> MockActionRecord:
        existing = self._records.get(idempotency_key)
        if existing is not None:
            return existing

        record = MockActionRecord(
            action_status=action_status,
            summary=summary,
            evidence_refs=list(evidence_refs or []),
            output_preview=dict(output_preview or {}),
        )
        self._records[idempotency_key] = record
        return record

    def get(self, idempotency_key: str) -> MockActionRecord | None:
        return self._records.get(idempotency_key)

    def query_action_status(self, idempotency_key: str) -> str:
        record = self.get(idempotency_key)
        return record.action_status if record is not None else "not_found"
