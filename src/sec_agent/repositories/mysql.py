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
            request_payload = ctx.request.model_dump(mode="json") if ctx.request is not None else None
            request_sample_id = ctx.request.sample_id if ctx.request is not None else None
            request_xdr_event_id = ctx.request.xdr_event_id if ctx.request is not None else None
            event_summary = ctx.event_summary.summary if ctx.event_summary else None
            alert_count = ctx.event_summary.alert_count_before if ctx.event_summary else len(ctx.alert_refs)
            risk_score = ctx.triage.risk_score if ctx.triage else None
            priority = ctx.triage.priority.value if ctx.triage else None
            verdict = ctx.triage.verdict.value if ctx.triage else None
            if existing is None:
                session.add(
                    SecurityEventRow(
                        event_id=ctx.event_id,
                        run_id=ctx.run_id,
                        trace_id=ctx.trace_id,
                        status=ctx.status.value,
                        source=ctx.source,
                        requested_source=ctx.requested_source,
                        effective_source=ctx.effective_source,
                        fallback_source=ctx.fallback_source,
                        sample_id=request_sample_id,
                        xdr_event_id=request_xdr_event_id,
                        alert_count=alert_count,
                        risk_score=risk_score,
                        priority=priority,
                        verdict=verdict,
                        summary=event_summary,
                        request_payload=request_payload,
                        payload=payload,
                    )
                )
            else:
                existing.run_id = ctx.run_id
                existing.trace_id = ctx.trace_id
                existing.status = ctx.status.value
                existing.source = ctx.source
                existing.requested_source = ctx.requested_source
                existing.effective_source = ctx.effective_source
                existing.fallback_source = ctx.fallback_source
                existing.sample_id = request_sample_id
                existing.xdr_event_id = request_xdr_event_id
                existing.alert_count = alert_count
                existing.risk_score = risk_score
                existing.priority = priority
                existing.verdict = verdict
                existing.summary = event_summary
                existing.request_payload = request_payload
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

    def delete(self, event_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(SecurityEventRow, event_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def claim_idempotency_key(self, key: str) -> bool:
        with self._session_factory() as session:
            return self._insert_idempotency_key(session, key)

    def has_idempotency_key(self, key: str) -> bool:
        with self._session_factory() as session:
            return session.get(IdempotencyKeyRow, key) is not None

    @staticmethod
    def _insert_idempotency_key(session: Session, key: str) -> bool:
        session.add(IdempotencyKeyRow(idempotency_key=key))
        try:
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False
