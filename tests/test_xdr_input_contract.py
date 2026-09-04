"""PR#22 契约结构测试 —— 已升级到官方真实字段（T0903-06 Chenmin 迁移后）。

PR#22 @ 2026-08-27 是 early-stage 契约草稿，字段名多为占位符。
main @ e154343（含 PR#33 @ e3cca8f）已对齐官方真实字段：
  - 请求：POST /api/xdr/v1/alerts/list + JSON body {page,pageSize,startTimestamp?}
  - 响应：data.item[]（单数字段）+ camelCase 字段 + severity:int + Unix 秒戳
  - 唯一标识：uuId（官方确认）
  - 签名：XdrOfficialSigner HMAC-SHA256

本测试是"结构守护"——确保 fixture 不回退到早期占位符、不引入真实凭据。
"""
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

    # ------------------------------------------------------------------
    # 1. 请求结构 → 官方 POST + JSON body 分页（不再是 PROVIDER_DEFINED 占位）
    # ------------------------------------------------------------------
    def test_request_is_official_post_body_pagination(self) -> None:
        """PR#22 旧：transport.method=PROVIDER_DEFINED；新：method=POST + 真实 path + JSON body。"""
        transport = self.request["transport"]
        self.assertEqual(transport["method"], "POST")
        self.assertEqual(transport["endpoint"], "/api/xdr/v1/alerts/list")
        body = self.request["body"]
        self.assertIn("page", body)
        self.assertIn("pageSize", body)
        # startTimestamp 可选，存在时必须是整数占位符
        if "startTimestamp" in body:
            self.assertIsInstance(body["startTimestamp"], str)  # 占位符字符串

    # ------------------------------------------------------------------
    # 2. 响应结构 → 官方 data.item[] + camelCase + severity:int + Unix 秒戳
    # ------------------------------------------------------------------
    def test_response_carries_official_item_array_and_camel_case(self) -> None:
        """PR#22 旧：data.records[] + snake_case；新：data.item[] + camelCase 官方字段。"""
        data = self.response["provider_response"]["data"]
        # ✅ 官方单数字段 item 存在
        self.assertIn("item", data)
        self.assertNotIn("records", data)
        self.assertIsInstance(data["item"], list)
        record = data["item"][0]

        # ✅ 必需三字段（官方真实字段名）
        self.assertIn("uuId", record, "官方唯一标识 uuId 必须存在")
        self.assertIn("name", record, "官方告警名 name 必须存在")
        # 时间三字段：Unix 秒戳（int）
        self.assertIn("lastTime", record, "lastTime 必须存在")
        self.assertIn("firstTime", record)
        self.assertIn("updateTime", record)

        # ✅ 官方 severity 是 int（50/70/90+），不是字符串 "高危"
        self.assertIn("severity", record)
        self.assertIsInstance(record["severity"], int, "官方 severity 必须是 int，不是字符串")

        # ✅ 数组字段（官方真实类型）
        self.assertIn("srcIp", record)
        self.assertIsInstance(record["srcIp"], list)
        self.assertIn("dstIp", record)
        self.assertIsInstance(record["dstIp"], list)
        self.assertIn("srcPort", record)
        self.assertIsInstance(record["srcPort"], list)
        self.assertIn("dstPort", record)
        self.assertIsInstance(record["dstPort"], list)

        # ✅ 官方威胁分类字段（event_type 推导链起点）
        self.assertIn("threatSubTypeDesc", record)
        self.assertIn("riskTag", record)
        self.assertIsInstance(record["riskTag"], list)
        self.assertIn("threatTypeDesc", record)
        self.assertIn("threatClassDesc", record)

        # ✅ 官方设备来源字段（source_device 回退链）
        self.assertIn("devSourceName", record)
        self.assertIsInstance(record["devSourceName"], list)
        self.assertIn("engineName", record)
        self.assertIsInstance(record["engineName"], list)

        # ✅ 官方证据追溯字段（traceBackId → EvidenceRef）
        self.assertIn("traceBackId", record)
        self.assertIsInstance(record["traceBackId"], list)

        # ✅ 脱敏检查：uuId 是占位符，不是真实值
        self.assertTrue(record["uuId"].startswith("<REDACTED_"))
        self.assertTrue(record["name"].startswith("<REDACTED_"))

    # ------------------------------------------------------------------
    # 3. adapter_expectations 升级到官方字段名
    # ------------------------------------------------------------------
    def test_adapter_expectations_align_with_official_fields(self) -> None:
        """PR#22 旧：affected_asset_rule=destination_ip_first_host_ip_fallback_only；
        新：dstIp_first_hostIp_fallback_only（官方 camelCase）。"""
        exp = self.response["adapter_expectations"]
        self.assertEqual(exp["stable_identifier_preference"][0], "uuId")
        self.assertEqual(exp["time_priority_preference"], ["lastTime", "firstTime", "updateTime"])
        self.assertEqual(exp["event_type_priority_preference"][0], "threatSubTypeDesc")
        self.assertTrue(exp["severity_numeric_preference"])
        self.assertEqual(exp["affected_asset_rule"], "dstIp_first_hostIp_fallback_only")
        self.assertEqual(
            exp["source_device_rule"],
            "devSourceName_first_engineName_then_devUidDesc_then_data_source_then_XDR",
        )
        # ✅ 空结果不是 transport failure 但应触发 empty_result error（PR#33 对齐）
        self.assertIn("empty_result_error", exp["empty_records_rule"])
        # ✅ 必需三字段已升级到官方名 uuId / lastTime / name
        self.assertIn("uuId", exp["record_rejection_rule"])
        self.assertIn("lastTime", exp["record_rejection_rule"])
        self.assertIn("name", exp["record_rejection_rule"])

    # ------------------------------------------------------------------
    # 4. 脱敏约束仍有效（PR#22 原始契约，结构不变）
    # ------------------------------------------------------------------
    def test_sample_never_claims_fixture_addresses_are_real_query_entities(self) -> None:
        serialized = json.dumps({"request": self.request, "response": self.response}, ensure_ascii=False)
        self.assertIn("not real query entities", serialized)
        self.assertNotIn("XDR_BASE_URL=", serialized)
        self.assertNotIn("Bearer ", serialized)


if __name__ == "__main__":
    unittest.main()
