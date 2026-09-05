from __future__ import annotations

from sec_agent.domain.models import EventContext


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[str, EventContext] = {}
        self._idempotency_keys: set[str] = set()

    def save(self, ctx: EventContext) -> EventContext:
        self._events[ctx.event_id] = ctx
        return ctx

    def get(self, event_id: str) -> EventContext | None:
        return self._events.get(event_id)

    def list(self) -> list[EventContext]:
        return list(self._events.values())

    def delete(self, event_id: str) -> bool:
        return self._events.pop(event_id, None) is not None

    def claim_idempotency_key(self, key: str) -> bool:
        if key in self._idempotency_keys:
            return False
        self._idempotency_keys.add(key)
        return True

    def has_idempotency_key(self, key: str) -> bool:
        return key in self._idempotency_keys
