from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text

from sec_agent.infrastructure.mysql.session import ensure_existing_schema


class MySQLSchemaMigrationTest(unittest.TestCase):
    def test_ensure_existing_schema_adds_missing_indexes(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE security_events (
                        event_id VARCHAR(80) NOT NULL PRIMARY KEY,
                        run_id VARCHAR(80) NOT NULL,
                        trace_id VARCHAR(80) NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        source VARCHAR(64) NOT NULL,
                        requested_source VARCHAR(64),
                        effective_source VARCHAR(64),
                        fallback_source VARCHAR(64),
                        sample_id VARCHAR(120),
                        xdr_event_id VARCHAR(160),
                        alert_count INTEGER,
                        risk_score INTEGER,
                        priority VARCHAR(32),
                        verdict VARCHAR(32),
                        summary TEXT,
                        request_payload JSON,
                        payload JSON NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )

        ensure_existing_schema(engine)

        indexes = {index["name"] for index in inspect(engine).get_indexes("security_events")}
        self.assertIn("ix_security_events_created_at", indexes)
        self.assertIn("ix_security_events_status", indexes)


if __name__ == "__main__":
    unittest.main()
