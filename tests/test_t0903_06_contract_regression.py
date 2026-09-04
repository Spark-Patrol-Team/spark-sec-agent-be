"""T0903-06 陈敏：字段契约迁移后的回归测试（第 3 步）。

覆盖 5 类场景：
  1. 脱敏真实结构转换（official_desensitized_alert.json → AlertRecord）
  2. 固定样例回归（FixedSampleAdapter 主链不被破坏）
  3. 缺字段处理（必需三缺一 → field_mapping，不降级）
  4. 空结果处理（data.item=[] → empty_result，不降级）
  5. 去重契约（跨页同 uuId、精确 lookup 本地过滤、关联压缩）
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sec_agent.domain.models import (
    AlertRecord,
    BusinessStatus,
    StartRunRequest,
)
from sec_agent.platforms.errors import PlatformIngestError
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.xdr_openapi import XdrOpenApiAdapter, XdrOpenApiConfig
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.orchestrator import Orchestrator


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "xdr_openapi"
with (FIXTURE_DIR / "official_desensitized_alert.json").open("r", encoding="utf-8") as f:
    OFFICIAL_ALERT = json.load(f)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._p = payload

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def send(self, prepared, timeout=None):
        self.calls.append({"url": prepared.url, "body": prepared.body, "headers": dict(prepared.headers)})
        return self.responses.pop(0) if self.responses else FakeResponse(200, {"code": "Success", "data": {"item": [], "total": 0}})


def cfg(**ov):
    base = dict(base_url="https://xdr.example.test", auth_type="aksk", access_key="ak-test", secret_key="sk-test",
                startup_check=False, preflight_http_check=False, allow_fixed_sample_fallback=False)
    base.update(ov)
    return XdrOpenApiConfig(**base)


def make_session(response_payload):
    return FakeSession([FakeResponse(200, response_payload)])


def wrap(item_or_items, total=1, page=1, page_size=50, code="Success", message="成功"):
    """把单条/多条告警包成官方 data.item 分页壳。"""
    if isinstance(item_or_items, list):
        items = item_or_items
    else:
        items = [item_or_items]
    return {"code": code, "message": message, "data": {"total": total, "page": page, "pageSize": page_size, "item": items}}


# ---------------------------------------------------------------------------
# 场景 1：脱敏真实结构转换
# ---------------------------------------------------------------------------
class T090306DesensitizedRealConversionTest(unittest.TestCase):
    """用 XDR_OpenAPI更新版(1).md 第五部分脱敏 JSON 逐字段核对转换结果。"""

    def setUp(self):
        session = make_session(wrap(OFFICIAL_ALERT))
        self.adapter = XdrOpenApiAdapter(cfg(), session=session)
        self.alerts = self.adapter.fetch_alerts(xdr_event_id="alert-REDACTED-UUID")
        self.alert = self.alerts[0]

    def test_basic_field_mapping(self):
        a = self.alert
        self.assertEqual(a.alert_id, "alert-REDACTED-UUID")
        self.assertEqual(a.name, "SQL server数据库查询sa账户密码攻击")
        self.assertEqual(a.alert_type, "sql_injection")
        self.assertEqual(a.raw_severity, "high")
        self.assertEqual(a.src_ip, "192.168.X.X")
        self.assertEqual(a.src_port, 12345)
        self.assertEqual(a.dst_ip, "192.168.Y.Y")
        self.assertEqual(a.dst_port, 80)
        self.assertEqual(a.assets, ["192.168.Y.Y"])
        self.assertEqual(a.source, "xdr_openapi")
        self.assertEqual(a.attack_status, "new")

    def test_last_time_takes_priority(self):
        """官方脱敏数据：firstTime=1700000000(08:53), lastTime=1700003600(09:53).
        PR33 已改为 lastTime 优先 → occurred_at 必须是 09:53。"""
        # expected: 2026-09-14 17:53 UTC + 8h → +08:00 = 09:53 local
        # fromtimestamp 取墙钟（PR33 代码逻辑），补 Asia/Shanghai
        import datetime as _dt
        expected = _dt.datetime.fromtimestamp(1700003600).replace(
            tzinfo=timezone(timedelta(hours=8))
        ).isoformat()
        self.assertEqual(self.alert.occurred_at.isoformat(), expected)

    def test_scenario_fields_have_expected_xdr_prefix(self):
        sf = self.alert.scenario_fields
        # 标准化字段（不带 xdr_）
        self.assertEqual(sf["source_device_type"], "XDR")
        self.assertEqual(sf["source_device_name"], "STA (REDACTED)")
        self.assertEqual(sf["evidence_source"], "xdr_security_alert")
        self.assertEqual(sf["sample_nature"], "platform_derived")
        # 原始字段（带 xdr_）
        self.assertEqual(sf["xdr_threatClassDesc"], "数据库攻击利用")
        self.assertEqual(sf["xdr_threatSubTypeDesc"], "SQL注入")
        self.assertEqual(sf["xdr_gptResultDescription"], "真实攻击成功")
        self.assertEqual(sf["xdr_attackState"], 2)       # 合法 int 0/2 保留
        self.assertEqual(sf["xdr_confidence"], 20)
        self.assertEqual(sf["xdr_alertDealAction"], "待处置")
        self.assertEqual(sf["xdr_whiteStatus"], "未加白")
        self.assertEqual(sf["xdr_logCount"], 21)
        self.assertEqual(sf["xdr_stage"], 30)

    def test_empty_arrays_filtered_out(self):
        """空数组 domain/xforwardedFor/hostGroupIds/hostGroups 不应进入 scenario_fields。"""
        sf = self.alert.scenario_fields
        self.assertNotIn("xdr_domain", sf)
        self.assertNotIn("xdr_xforwardedFor", sf)
        self.assertNotIn("xdr_hostGroupIds", sf)
        self.assertNotIn("xdr_hostGroups", sf)

    def test_null_scalars_filtered_out(self):
        """null scalar pname/fileMd5/exploitCveId 不应进入 scenario_fields。"""
        sf = self.alert.scenario_fields
        self.assertNotIn("xdr_pname", sf)
        self.assertNotIn("xdr_fileMd5", sf)
        self.assertNotIn("xdr_exploitCveId", sf)

    def test_traceback_preserved_as_evidence(self):
        """traceBackId 必须追加为 xdr_traceback EvidenceRef。"""
        tb = [e for e in self.alert.evidence_refs if e.kind == "xdr_traceback"]
        self.assertEqual(len(tb), 1)
        self.assertEqual(tb[0].ref_id, "alert-REDACTED-UUID:traceBackId:network_security_log-REDACTED")
        self.assertEqual(tb[0].source, "xdr_security_alert")

    def test_url_nonempty_array_preserved(self):
        """非空数组 url 应留存（与空数组过滤区分）。"""
        self.assertEqual(self.alert.scenario_fields["xdr_url"], ["http://example.local/path"])

    def test_full_main_chain_to_approval_required(self):
        """脱敏真实结构 → 完整主链 APPROVAL_REQUIRED，无 fallback。

        investigation_backend 固定 tool_mock：主链状态与 deep_agent/LLM 环境解耦，
        避免开发机配置 LLM 凭据/DEEP_AGENT_TOOL_MODE 时走真实深度调查导致非确定性。
        """
        session = make_session(wrap(OFFICIAL_ALERT))
        orch = Orchestrator(platform=XdrOpenApiAdapter(cfg(), session=session),
                            store=InMemoryEventRepository(),
                            investigation_backend="tool_mock")
        ctx = orch.start(StartRunRequest(source="xdr", xdr_event_id="alert-REDACTED-UUID"))
        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        self.assertIsNone(ctx.fallback_source)
        self.assertEqual(ctx.alert_refs, ["alert-REDACTED-UUID"])
        self.assertEqual(ctx.errors, [])
        # timeline 六状态
        statuses = [e.status.value for e in ctx.timeline]
        for expected in ["RECEIVED", "CORRELATING", "TRIAGED", "INVESTIGATING",
                          "DECISION_READY", "APPROVAL_REQUIRED"]:
            self.assertIn(expected, statuses, f"缺少状态 {expected}")


# ---------------------------------------------------------------------------
# 场景 2：固定样例回归
# ---------------------------------------------------------------------------
class T090306FixedSampleRegressionTest(unittest.TestCase):
    """FixedSampleAdapter 必须还能跑完整主链，不被 XDR 契约改造破坏。"""

    def test_fixed_sample_adapter_returns_two_alerts(self):
        a = FixedSampleAdapter()
        alerts = a.fetch_alerts(sample_id="webshell-001")
        self.assertEqual(len(alerts), 2)
        for al in alerts:
            self.assertIsInstance(al, AlertRecord)
            self.assertTrue(al.alert_id.startswith("xdr-alert-00"))
            self.assertEqual(al.source, "fixed_sample")

    def test_fixed_sample_main_chain_to_approval_required(self):
        # investigation_backend 固定 tool_mock：与 deep_agent/LLM 环境解耦（见 test_state_flow.py 既有模式）
        orch = Orchestrator(platform=FixedSampleAdapter(), store=InMemoryEventRepository(),
                            platform_backend="fixed_sample",
                            investigation_backend="tool_mock")
        ctx = orch.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.effective_source, "fixed_sample")
        self.assertIsNone(ctx.fallback_source)


# ---------------------------------------------------------------------------
# 场景 3：缺字段处理（必需三缺一）
# ---------------------------------------------------------------------------
class T090306MissingRequiredFieldsTest(unittest.TestCase):
    """缺少 event_id / event_time / alert_name 任一 → 直接失败，不降级。"""

    def _fetch(self, raw):
        session = make_session(wrap(raw))
        adapter = XdrOpenApiAdapter(cfg(), session=session)
        return adapter.fetch_alerts()

    def test_missing_uuId_raises(self):
        bad = {k: v for k, v in OFFICIAL_ALERT.items() if k != "uuId"}
        with self.assertRaises(PlatformIngestError) as ctx:
            self._fetch(bad)
        self.assertIn("field_mapping", str(ctx.exception))
        self.assertFalse(ctx.exception.allow_fallback)

    def test_missing_firstTime_lastTime_updateTime_all_raises(self):
        bad = {k: v for k, v in OFFICIAL_ALERT.items()
               if k not in {"firstTime", "lastTime", "updateTime"}}
        with self.assertRaises(PlatformIngestError):
            self._fetch(bad)

    def test_missing_name_raises(self):
        bad = {k: v for k, v in OFFICIAL_ALERT.items() if k != "name"}
        with self.assertRaises(PlatformIngestError):
            self._fetch(bad)

    def test_field_mapping_error_does_not_fallback(self):
        """缺必需字段 → field_mapping error，即使 allow_fixed_sample_fallback=True 也不降级。"""
        bad = {k: v for k, v in OFFICIAL_ALERT.items() if k != "uuId"}
        session = make_session(wrap(bad))
        adapter = XdrOpenApiAdapter(cfg(allow_fixed_sample_fallback=True), session=session)
        with self.assertRaises(PlatformIngestError):
            adapter.fetch_alerts()

    def test_business_code_fail_raises(self):
        """业务 code != Success → 直接 raise，不降级。"""
        session = make_session({"code": "Fail", "message": "签名错误", "data": None})
        adapter = XdrOpenApiAdapter(cfg(allow_fixed_sample_fallback=True), session=session)
        with self.assertRaises(PlatformIngestError) as ctx:
            adapter.fetch_alerts()
        self.assertIn("platform_error", str(ctx.exception))


# ---------------------------------------------------------------------------
# 场景 4：空结果处理
# ---------------------------------------------------------------------------
class T090306EmptyResultTest(unittest.TestCase):
    """data.item=[] + total=0 → empty_result，不降级。"""

    def test_empty_item_raises_empty_result(self):
        session = make_session({"code": "Success", "data": {"total": 0, "page": 1, "pageSize": 50, "item": []}})
        adapter = XdrOpenApiAdapter(cfg(), session=session)
        with self.assertRaises(PlatformIngestError) as ctx:
            adapter.fetch_alerts()
        self.assertIn("empty_result", str(ctx.exception))

    def test_empty_item_does_not_fallback_even_when_enabled(self):
        session = make_session({"code": "Success", "data": {"total": 0, "item": []}})
        adapter = XdrOpenApiAdapter(cfg(allow_fixed_sample_fallback=True), session=session)
        with self.assertRaises(PlatformIngestError):
            adapter.fetch_alerts()


# ---------------------------------------------------------------------------
# 场景 5：去重契约
# ---------------------------------------------------------------------------
class T090306DeduplicationTest(unittest.TestCase):
    """跨页同 uuId 去重 + 精确 lookup 本地过滤 + 关联压缩。"""

    def test_cross_page_same_uuid_deduplicated(self):
        a1 = dict(OFFICIAL_ALERT, uuId="dup-uuid")
        a2 = dict(OFFICIAL_ALERT, uuId="dup-uuid", name="第二次出现")
        session = FakeSession([
            FakeResponse(200, wrap(a1, total=2)),
            FakeResponse(200, wrap(a2, total=2, page=2)),
        ])
        alerts = XdrOpenApiAdapter(cfg(), session=session).fetch_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].name, "SQL server数据库查询sa账户密码攻击")  # 取第一次

    def test_exact_lookup_filters_non_matching_uuid(self):
        session = make_session(wrap([
            dict(OFFICIAL_ALERT, uuId="alert-OTHER-UUID"),
            dict(OFFICIAL_ALERT, uuId="alert-TARGET-UUID"),
        ], total=2))
        alerts = XdrOpenApiAdapter(cfg(), session=session).fetch_alerts(
            xdr_event_id="alert-TARGET-UUID")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_id, "alert-TARGET-UUID")

    def test_correlation_compresses_same_type_window(self):
        from datetime import timezone as _tz
        alerts = []
        for i in range(3):
            alerts.append(AlertRecord(
                alert_id=f"corr-a-{i}", source="xdr_openapi",
                occurred_at=datetime(2026, 9, 3, 9, i, tzinfo=_tz(timedelta(hours=8))),
                name="SQL注入", alert_type="sql_injection", raw_severity="medium",
                src_ip="10.10.10.1", dst_ip="10.10.10.2",
                assets=["10.10.10.2"],
                scenario_fields={"source_device_name": "XDR"},
                raw_record_ref=f"xdr://#corr{i}",
            ))
        evt = AlertCorrelationService(window_minutes=15).correlate(alerts)
        self.assertEqual(evt.alert_count_before, 3)
        self.assertEqual(evt.event_count_after, 1)
        self.assertEqual(evt.entities["src_ips"], ["10.10.10.1"])

    def test_correlation_rejects_mismatched_type(self):
        from datetime import timezone as _tz
        base = dict(source="xdr_openapi", src_ip="1.1.1.1", dst_ip="2.2.2.2",
                    assets=["srv"], scenario_fields={"source_device_name": "XDR"},
                    raw_record_ref="x", name="测试告警", raw_severity="medium")
        a1 = AlertRecord(**base, alert_id="e1", alert_type="sql_injection",
                         occurred_at=datetime(2026, 9, 3, 9, 0, tzinfo=_tz(timedelta(hours=8))))
        a2 = AlertRecord(**base, alert_id="e2", alert_type="webshell",
                         occurred_at=datetime(2026, 9, 3, 9, 1, tzinfo=_tz(timedelta(hours=8))))
        with self.assertRaises(ValueError):
            AlertCorrelationService(window_minutes=15).correlate([a1, a2])


class T090306EventTypeNameFallbackTest(unittest.TestCase):
    """闫昱硕 2026-09-04 反馈：官方分类为「异常操作」时 name 回退应识别 SQL 注入。"""

    def test_official_abnormal_operation_falls_back_to_sqli_by_name(self):
        raw = dict(OFFICIAL_ALERT)
        raw["threatSubTypeDesc"] = "异常操作"
        raw["riskTag"] = ["异常操作"]
        raw["threatTypeDesc"] = "异常操作"
        session = make_session(wrap(raw))
        alerts = XdrOpenApiAdapter(cfg(), session=session).fetch_alerts(xdr_event_id=raw["uuId"])
        self.assertEqual(alerts[0].alert_type, "sql_injection")

    def test_name_only_sa_password_attack_maps_to_sqli(self):
        from sec_agent.platforms.raw_jsonl import RawJsonlNormalizer

        result = RawJsonlNormalizer._event_type(
            None, None, None, None, None, "SQL server数据库查询sa账户密码攻击"
        )
        self.assertEqual(result, "sql_injection")


if __name__ == "__main__":
    unittest.main()
