from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from sec_agent.domain.models import (
    BusinessStatus,
    EventContext,
    SecurityEvent,
    StartRunRequest,
    TriageResult,
    TruthVerdict,
    Priority,
)
from sec_agent.repositories.mysql import MySQLEventRepository


def sqlite_dsn(path: Path) -> str:
    return f"sqlite+pysqlite:///{path}"


def make_context(event_id: str = "evt-mysql-001") -> EventContext:
    return EventContext(
        trace_id="trace-mysql-001",
        run_id="run-mysql-001",
        event_id=event_id,
        status=BusinessStatus.APPROVAL_REQUIRED,
        source="xdr",
        request=StartRunRequest(source="xdr", xdr_event_id="alert-xdr-001"),
        requested_source="xdr",
        effective_source="xdr_openapi",
        fallback_source=None,
        alert_refs=["alert-xdr-001", "alert-xdr-002"],
        event_summary=SecurityEvent(
            event_id=event_id,
            alert_refs=["alert-xdr-001", "alert-xdr-002"],
            first_seen_at=datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 9, 5, 1, 5, tzinfo=timezone.utc),
            correlation_reason="测试关联",
            alert_count_before=2,
            event_count_after=1,
            summary="测试事件摘要",
        ),
        triage=TriageResult(
            verdict=TruthVerdict.MALICIOUS,
            confidence=0.85,
            risk_score=80,
            priority=Priority.HIGH,
            should_investigate=True,
            summary="测试研判摘要",
        ),
    )


class MySQLEventRepositoryTest(unittest.TestCase):
    def test_save_get_list_and_delete_with_request_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = MySQLEventRepository(sqlite_dsn(Path(tmpdir) / "events.db"))
            ctx = make_context()

            repo.save(ctx)

            loaded = repo.get(ctx.event_id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.event_id, ctx.event_id)
            self.assertEqual(loaded.request, ctx.request)
            self.assertEqual(loaded.triage.risk_score, 80)
            self.assertEqual([item.event_id for item in repo.list()], [ctx.event_id])

            with repo._engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT requested_source, effective_source, sample_id, xdr_event_id, "
                        "alert_count, risk_score, priority, verdict, request_payload "
                        "FROM security_events WHERE event_id = :event_id"
                    ),
                    {"event_id": ctx.event_id},
                ).mappings().one()
            self.assertEqual(row["requested_source"], "xdr")
            self.assertEqual(row["effective_source"], "xdr_openapi")
            self.assertIsNone(row["sample_id"])
            self.assertEqual(row["xdr_event_id"], "alert-xdr-001")
            self.assertEqual(row["alert_count"], 2)
            self.assertEqual(row["risk_score"], 80)
            self.assertEqual(row["priority"], "high")
            self.assertEqual(row["verdict"], "malicious")
            self.assertIn("alert-xdr-001", str(row["request_payload"]))

            self.assertTrue(repo.delete(ctx.event_id))
            self.assertIsNone(repo.get(ctx.event_id))
            self.assertFalse(repo.delete(ctx.event_id))

    def test_auto_schema_upgrade_adds_missing_request_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "old.db"
            engine = create_engine(sqlite_dsn(db_path), future=True)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE security_events (
                            event_id VARCHAR(80) PRIMARY KEY,
                            run_id VARCHAR(80) NOT NULL,
                            trace_id VARCHAR(80) NOT NULL,
                            status VARCHAR(32) NOT NULL,
                            source VARCHAR(64) NOT NULL,
                            summary TEXT,
                            payload JSON NOT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        CREATE TABLE idempotency_keys (
                            idempotency_key VARCHAR(160) PRIMARY KEY,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )

            repo = MySQLEventRepository(sqlite_dsn(db_path), auto_create_schema=True)
            columns = {column["name"] for column in inspect(repo._engine).get_columns("security_events")}

            self.assertIn("request_payload", columns)
            self.assertIn("sample_id", columns)
            self.assertIn("xdr_event_id", columns)
            self.assertIn("risk_score", columns)


if __name__ == "__main__":
    unittest.main()
