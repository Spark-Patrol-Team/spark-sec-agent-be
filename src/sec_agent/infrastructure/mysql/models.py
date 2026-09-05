from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SecurityEventRow(Base):
    __tablename__ = "security_events"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    effective_source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fallback_source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sample_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    xdr_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    alert_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
