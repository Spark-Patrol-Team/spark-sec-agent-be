from __future__ import annotations

from typing import Protocol

from sec_agent.domain.models import EventContext


class EventRepository(Protocol):
    def save(self, ctx: EventContext) -> EventContext:
        raise NotImplementedError

    def get(self, event_id: str) -> EventContext | None:
        raise NotImplementedError

    def list(self) -> list[EventContext]:
        raise NotImplementedError

    def claim_idempotency_key(self, key: str) -> bool:
        raise NotImplementedError

