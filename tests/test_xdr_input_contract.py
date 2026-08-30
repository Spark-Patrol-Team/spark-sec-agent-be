from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "xdr_contract"


class TestXdrInputContractFixtures(unittest.TestCase):
    def setUp(self) -> None:
        self.request = json.loads(
            (FIXTURE_DIR / "xdr_list_alerts_request_sanitized.json").read_text(encoding="utf-8")
        )
        self.response = json.loads(
            (FIXTURE_DIR / "xdr_list_alerts_response_sanitized.json").read_text(encoding="utf-8")
        )

    def test_request_declares_runtime_only_transport_and_pagination(self) -> None:
        self.assertEqual(self.request["purpose"], "structure_only_for_local_xdr_adapter_validation")
        transport = self.request["transport"]
        self.assertEqual(transport["endpoint"], "PROVIDER_DEFINED_NOT_COMMITTED")
        self.assertEqual(transport["authentication"], "LOCAL_ENV_OR_SECRET_STORE_ONLY")
        query = self.request["query"]
        self.assertIn("start_time", query["time_range"])
        self.assertIn("end_time", query["time_range"])
        self.assertEqual(query["pagination"]["strategy"], "PROVIDER_DEFINED_PAGE_OR_CURSOR")

    def test_response_carries_minimum_xdr_record_shape_without_real_identifiers(self) -> None:
        record = self.response["provider_response"]["data"]["records"][0]
        expected_fields = {
            "event_id",
            "alert_id",
            "alert_time",
            "alert_name",
            "alert_grade",
            "source_ip",
            "destination_ip",
            "host_ip",
            "data_source",
            "evidence_ids",
        }
        self.assertTrue(expected_fields.issubset(record))
        self.assertEqual(record["data_source"], "XDR")
        self.assertTrue(record["event_id"].startswith("<REDACTED_"))
        self.assertTrue(record["alert_id"].startswith("<REDACTED_"))
        self.assertTrue(record["asset_id"].startswith("<REDACTED_"))

    def test_contract_preserves_existing_asset_and_empty_result_rules(self) -> None:
        expectations = self.response["adapter_expectations"]
        self.assertEqual(expectations["affected_asset_rule"], "destination_ip_first_host_ip_fallback_only")
        self.assertEqual(expectations["source_device_rule"], "source_device_name_then_data_source_then_XDR")
        self.assertEqual(expectations["empty_records_rule"], "success_with_zero_records_not_transport_failure")

    def test_sample_never_claims_fixture_addresses_are_real_query_entities(self) -> None:
        serialized = json.dumps({"request": self.request, "response": self.response}, ensure_ascii=False)
        self.assertIn("not real query entities", serialized)
        self.assertNotIn("XDR_BASE_URL=", serialized)
        self.assertNotIn("Bearer ", serialized)


if __name__ == "__main__":
    unittest.main()
