from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sec_agent.domain.models import EventContext
from sec_agent.infrastructure.mysql.models import IdempotencyKeyRow, SecurityEventRow
from sec_agent.infrastructure.mysql.session import create_mysql_engine, create_schema, session_factory


class MySQLEventRepository:
    def __init__(self, dsn: str, auto_create_schema: bool = True) -> None:
        self._engine = create_mysql_engine(dsn)
        if auto_create_schema:
            create_schema(self._engine)
        self._session_factory = session_factory(self._engine)

    def save(self, ctx: EventContext) -> EventContext:
        with self._session_factory() as session:
            existing = session.get(SecurityEventRow, ctx.event_id)
            payload = ctx.model_dump(mode="json")
            if existing is None:
                session.add(
                    SecurityEventRow(
                        event_id=ctx.event_id,
                        run_id=ctx.run_id,
                        trace_id=ctx.trace_id,
                        status=str(ctx.status),
                        source=ctx.source,
                        summary=ctx.event_summary.summary if ctx.event_summary else None,
                        payload=payload,
                    )
                )
            else:
                existing.run_id = ctx.run_id
                existing.trace_id = ctx.trace_id
                existing.status = str(ctx.status)
                existing.source = ctx.source
                existing.summary = ctx.event_summary.summary if ctx.event_summary else None
                existing.payload = payload
            session.commit()
        return ctx

    def get(self, event_id: str) -> EventContext | None:
        with self._session_factory() as session:
            row = session.get(SecurityEventRow, event_id)
            if row is None:
                return None
            return EventContext.model_validate(row.payload)

    def list(self) -> list[EventContext]:
        with self._session_factory() as session:
            rows = session.scalars(select(SecurityEventRow).order_by(SecurityEventRow.created_at.desc())).all()
            return [EventContext.model_validate(row.payload) for row in rows]

    def claim_idempotency_key(self, key: str) -> bool:
        with self._session_factory() as session:
            return self._insert_idempotency_key(session, key)

    @staticmethod
    def _insert_idempotency_key(session: Session, key: str) -> bool:
        session.add(IdempotencyKeyRow(idempotency_key=key))
        try:
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False

