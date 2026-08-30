from __future__ import annotations

import unittest
from datetime import datetime

from sec_agent.domain.models import AlertRecord
from sec_agent.platforms.xdr_openapi import XdrOpenApiAdapter, XdrOpenApiConfig


class T0828XdrFieldMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = XdrOpenApiAdapter(
            XdrOpenApiConfig(base_url="https://xdr.example.test", token="placeholder", startup_check=False)
        )

    def test_real_item_shape_maps_to_existing_alert_record(self) -> None:
        raw = {
            "uuId": "placeholder-alert-001",
            "firstTime": 1767000000,
            "lastTime": 1767000065000,
            "name": "WebShell蚁剑工具文件管理",
            "severity": 95,
            "srcIp": ["192.0.2.10"],
            "srcPort": [443],
            "dstIp": ["198.51.100.20"],
            "dstPort": [8080],
            "hostIp": "198.51.100.20",
            "devSourceName": "XDR-PLACEHOLDER",
            "traceBackId": "placeholder-trace-001",
            "attackStage": "initial_access",
            "platformConfidence": 0.91,
            "gptJudgement": "placeholder-only",
        }

        record = self.adapter._to_alert_record(raw)

        self.assertIsInstance(record, AlertRecord)
        self.assertEqual(record.alert_id, "placeholder-alert-001")
        self.assertEqual(record.src_ip, "192.0.2.10")
        self.assertEqual(record.dst_ip, "198.51.100.20")
        self.assertEqual(record.src_port, 443)
        self.assertEqual(record.dst_port, 8080)
        self.assertEqual(record.attack_status, "new")
        self.assertEqual(record.scenario_fields["attack_stage"], "initial_access")
        self.assertEqual(record.scenario_fields["platform_confidence"], 0.91)
        self.assertTrue(any(ref.ref_id.endswith(":traceBackId") for ref in record.evidence_refs))
        self.assertTrue(record.occurred_at.tzinfo)

    def test_host_ip_is_destination_fallback_and_duplicate_keeps_complete_item(self) -> None:
        sparse = {"uuId": "placeholder-alert-002", "name": "未授权访问", "lastTime": 1767000000, "hostIp": "198.51.100.21"}
        complete = {**sparse, "dstIp": ["198.51.100.22"], "severity": "高危", "devSourceName": "XDR-PLACEHOLDER"}
        merged = self.adapter._dedupe_items([sparse, complete])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["dstIp"], ["198.51.100.22"])
        normalized = self.adapter._to_alert_record(merged[0])
        self.assertEqual(normalized.dst_ip, "198.51.100.21")

    def test_page_item_extraction_and_stable_id_deduplication(self) -> None:
        page_one = {"code": "Success", "message": "成功", "data": {"item": [{"uuId": "a"}, {"uuId": "b"}]}}
        page_two = {"code": "Success", "message": "成功", "data": {"item": [{"uuId": "b", "name": "more-complete"}, {"uuId": "c"}]}}
        items = self.adapter._dedupe_items(self.adapter._extract_items(page_one) + self.adapter._extract_items(page_two))
        self.assertEqual([item["uuId"] for item in items], ["a", "b", "c"])
        self.assertEqual(items[1]["name"], "more-complete")

    def test_invalid_port_and_missing_stable_id_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter._to_normalizer_raw({"uuId": "x", "name": "告警", "lastTime": 1767000000, "srcPort": [70000]})
        with self.assertRaises(ValueError):
            self.adapter._dedupe_items([{"name": "没有稳定标识"}])


if __name__ == "__main__":
    unittest.main()
