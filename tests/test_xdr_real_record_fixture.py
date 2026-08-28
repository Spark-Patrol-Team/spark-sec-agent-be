import json
import unittest
from pathlib import Path

from sec_agent.domain.models import AlertRecord, NormalizedAlertRecord
from sec_agent.services.correlation import AlertCorrelationService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "xdr_contract" / "real_alert_records_sanitized.json"


class XdrRealRecordFixtureTest(unittest.TestCase):
    def test_sanitized_real_record_pair_matches_existing_contracts(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        normalized = NormalizedAlertRecord.model_validate(payload["normalized"])
        alert = AlertRecord.model_validate(payload["alert_record"])
        self.assertEqual(normalized.event_id, alert.alert_id)
        self.assertEqual(normalized.affected_asset, alert.assets[0])
        self.assertEqual(normalized.event_time, alert.occurred_at)
        self.assertEqual(normalized.severity, alert.raw_severity)

    def test_sanitized_real_record_enters_existing_correlation_chain(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        alert = AlertRecord.model_validate(payload["alert_record"])
        event = AlertCorrelationService(window_minutes=15).correlate([alert])
        self.assertEqual(event.alert_refs, ["xdr-alert-REDACTED-001"])
        self.assertEqual(event.entities["assets"], ["198.51.100.20"])
        self.assertEqual(event.event_count_after, 1)


if __name__ == "__main__":
    unittest.main()
