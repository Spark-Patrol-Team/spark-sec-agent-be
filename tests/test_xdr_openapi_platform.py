"""XDR OpenAPI 平台接入测试。

接线层（李雨妍职责）：官方签名 / POST /api/xdr/v1/alerts/list / 分页遍历 / 本地 uuId 筛选。
字段映射层（陈敏职责）：在 tests/test_t0828_* 和 tests/test_raw_jsonl_ingest_and_correlation.py 中已覆盖。
"""
from __future__ import annotations

import json
import unittest
from collections import deque
from unittest.mock import patch

import requests

from sec_agent.domain.models import (
    AlertRecord,
    BusinessStatus,
    ToolCallStatus,
    ToolRequest,
    ToolResult,
    ToolRiskLevel,
    ToolSideEffectType,
    utc_now,
    StartRunRequest,
)
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.xdr_openapi import (
    OfficialXdrSigner,
    PlatformResultCode,
    XdrOpenApiAdapter,
    XdrOpenApiConfig,
)
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.orchestrator import Orchestrator


# --------------------------------------------------------------------------- helpers
class FakeResponse:
    """简单模拟 response：status_code + json()。"""

    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """模拟 httpx.Client / requests.Session。支持多响应队列、注入异常、记录 calls。

    calls 中每项格式：(method: str, url: str, kwargs: dict)。
    """

    def __init__(
        self,
        response: FakeResponse | None = None,
        responses: list[FakeResponse] | None = None,
        exc: Exception | None = None,
    ) -> None:
        # responses 是队列（先进先出），每次请求弹出一个；如果传了单个 response 就自动放入队列
        self._queue: deque[FakeResponse] = deque()
        if responses:
            self._queue.extend(responses)
        elif response is not None:
            self._queue.append(response)
        self.exc = exc
        self.calls: list[tuple[str, str, dict]] = []

    # FakeSession：对外统一 post/get/request，内部记录 kwargs
    def _dispatch(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.exc:
            raise self.exc
        if not self._queue:
            raise AssertionError(f"FakeSession 响应队列已空：新请求 {method} {url}（已调用次数={len(self.calls)}）")
        return self._queue.popleft()

    def post(self, url, **kwargs):
        return self._dispatch("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._dispatch("GET", url, **kwargs)

    def request(self, method, url, **kwargs):
        return self._dispatch(method.upper(), url, **kwargs)


def xdr_config(**overrides) -> XdrOpenApiConfig:
    """单元测试默认用 token 模式，避免 pycryptodome/签名头构造。aksk 专项测试才显式切换。"""
    values = {
        "base_url": "https://xdr.example.test",
        "auth_type": "token",
        "token": "unit-test-token",
        "startup_check": True,
        "preflight_http_check": False,  # 默认关掉 HTTP 预检，专项测试再单独开
    }
    values.update(overrides)
    return XdrOpenApiConfig(**values)


# --------------------------------------------------------------------------- 真实XDR fixture（脱敏）
def _real_xdr_webshell_payload(total: int = 1, extra_items: list[dict] | None = None) -> dict:
    """与《脱敏接口契约》一致的 data.item 包装 + risk_score_seed=95 WebShell 脱敏样例。"""
    items = [
        {
            "uuId": "REAL-XDR-WEBSHELL-001",
            "eventName": "WebShell蚁剑工具文件管理",
            "severity": 95,  # 数值严重度（≥90 → critical）
            "srcIp": "198.51.100.33",
            "dstIp": "198.51.100.11",
            "srcPort": 51234,
            "dstPort": 8080,
            "hostIp": "198.51.100.11",
            "firstTime": 1787155200,
            "lastTime": 1787158800,
            "branchName": "XDR总部",
            "dataSource": "XDR",
            "attackState": "1",  # new
            "platformConfidence": 95,
            "attackStage": "Web权限维持",
            "gptJudgement": "高置信WebShell通信",
            "traceBackId": "TB-20260819-0001",
            "eventType": "Web安全",
            "destinationAssetName": "web-server-01",
            "riskScoreSeed": 95,
        }
    ]
    if extra_items:
        items.extend(extra_items)
    return {"data": {"total": total, "item": items}}


# --------------------------------------------------------------------------- 测试类
class XdrOpenApiPlatformTest(unittest.TestCase):
    # -------------------------------------------------------------------------- 基础工具断言
    @staticmethod
    def _assert_post_body_default(call) -> None:
        """call 必须是 POST 且 body 含默认 page/pageSize/startTimestamp。"""
        method, url, kwargs = call
        assert method == "POST", f"方法应为 POST，实际 {method}"
        # 新发送路径：json_body 作为 `json=` 传入 FakeSession
        body = kwargs.get("json") or {}
        assert body.get("page") == 1, f"page 应为 1，实际 {body.get('page')}"
        assert body.get("pageSize") == 50, f"pageSize 应为 50，实际 {body.get('pageSize')}"
        assert body.get("startTimestamp") == 1787155200, (
            f"startTimestamp 应为 1787155200，实际 {body.get('startTimestamp')}"
        )
        # 定向模式禁止塞 event_id 到请求参数（必须本地筛选）
        assert "event_id" not in (kwargs.get("params") or {}), "禁止把 xdr_event_id 塞进 URL params（第三步第6条）"
        assert "event_id" not in body, "禁止把 xdr_event_id 塞进请求 body（第三步第6条）"
        # URL 前缀必须对
        assert "/api/xdr/v1/alerts/list" in url, (
            f"真实只读接口应为 /api/xdr/v1/alerts/list，实际 URL={url}"
        )

    # -------------------------------------------------------------------------- 端到端主流程
    def test_real_xdr_alert_continues_existing_main_chain(self) -> None:
        """真实 XDR 告警进入主链：source=xdr、effective_source=xdr_openapi、APPROVAL_REQUIRED。"""
        # 响应队列：fetch_alerts page1（pageSize=50） + 后续 xdr_log_query 默认 HTTP 处理
        responses = [
            FakeResponse(200, _real_xdr_webshell_payload(total=1)),
            FakeResponse(200, {"data": {"items": [{"rule_name": "调查补充日志"}]}}),
        ]
        session = FakeSession(responses=responses)
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-WEBSHELL-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.source, "xdr")
        self.assertEqual(ctx.requested_source, "xdr")
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        self.assertIsNone(ctx.fallback_source)
        self.assertEqual(ctx.alert_refs, ["REAL-XDR-WEBSHELL-001"])
        self.assertEqual(ctx.triage.risk_score, 95)  # risk_score_seed=95 → seed 胜出
        self.assertEqual(ctx.response.plan.target, "198.51.100.11")  # dstIp
        self.assertTrue(session.calls, "至少调用过一次 HTTP")
        # 定向模式：page=1 / pageSize=50 / startTimestamp=1787155200（默认参数）
        # 且 event_id **不**出现在请求体
        preflight_calls = [c for c in session.calls if c[2].get("json", {}).get("pageSize") == 1]
        fetch_calls = [c for c in session.calls if c[2].get("json", {}).get("pageSize") == 50]
        self.assertTrue(fetch_calls, "未找到分页 fetch 调用")
        self._assert_post_body_default(fetch_calls[0])
        # 预检（如果开启的话）和 fetch 必须都用 POST
        self.assertTrue(all(c[0] == "POST" for c in session.calls), "所有 HTTP 调用应为 POST")

    # -------------------------------------------------------------------------- 失败不降级 / 可降级
    def test_auth_failure_fails_without_fixed_sample_fallback(self) -> None:
        """首页返回 401（auth 类）：即使 allow_fixed_sample_fallback=True 也不降级。"""
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(response=FakeResponse(401, {"message": "unauthorized"})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-001"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertTrue(ctx.trace_id.startswith("trace-"))
        # 必须不得降级：ctx.effective_source 不应该是 fixed_sample_fallback
        self.assertNotEqual(ctx.effective_source, "fixed_sample_fallback",
                            "401（AUTH_FAILURE）不允许降级到 fixed_sample")
        # errors[0].message 必须包含 auth/client_error_status_401/鉴权
        combined_errors = " | ".join(str(e.message) for e in ctx.errors)
        self.assertTrue(
            ("auth" in combined_errors.lower()) or ("鉴权" in combined_errors) or ("client_error_status_401" in combined_errors),
            f"errors 中没有 auth/鉴权相关错误：{ctx.errors}",
        )

    def test_timeout_can_fallback_to_fixed_sample_when_enabled(self) -> None:
        """首页 requests.Timeout：allow_fixed_sample_fallback=True → 切 FixedSample。"""
        # 注入 xdr_log_query_handler：降级后我们不关心日志查询的真实HTTP，避免 session exc 再次抛出污染状态
        def _ok_log_handler(req: ToolRequest) -> ToolResult:
            now = utc_now()
            return ToolResult(
                call_id=req.call_id, trace_id=req.trace_id, event_id=req.event_id,
                tool_name=req.tool_name, action_name=req.action_name,
                idempotency_key=req.idempotency_key, status=ToolCallStatus.SUCCESS,
                summary="fallback-mode xdr log stub",
                raw_result_ref="xdr://stub-fallback/logs",
                output_preview={"records": []},
                side_effect_type=ToolSideEffectType.READ_ONLY,
                started_at=now, ended_at=now, duration_ms=0,
            )
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(exc=requests.Timeout("read timeout")),
            fallback_adapter=FixedSampleAdapter(),
            xdr_log_query_handler=_ok_log_handler,
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.source, "xdr")
        self.assertEqual(ctx.requested_source, "xdr")
        self.assertEqual(ctx.effective_source, "fixed_sample_fallback")
        self.assertEqual(ctx.fallback_source, "fixed_sample")
        # timeline 第一条是"已接收；已降级"
        self.assertIn("已降级", ctx.timeline[0].message)
        # errors 中需含 timeout
        self.assertTrue(
            any("timeout" in str(e.message).lower() for e in ctx.errors),
            f"errors 中没有 timeout：{ctx.errors}",
        )

    def test_empty_result_fails_without_fallback(self) -> None:
        """空 data.item：FAILED，errors 含 empty_result（定向 xdr_event_id 时仍应为 empty_result，候选集为空）。"""
        empty_payload = {"data": {"total": 0, "item": []}}
        # 注入 xdr_log_query_handler 以免 session 队列被第二个真实 HTTP 再次消耗
        def _ok_log_handler(req: ToolRequest) -> ToolResult:
            now = utc_now()
            return ToolResult(
                call_id=req.call_id, trace_id=req.trace_id, event_id=req.event_id,
                tool_name=req.tool_name, action_name=req.action_name,
                idempotency_key=req.idempotency_key, status=ToolCallStatus.SUCCESS,
                summary="stub", raw_result_ref="xdr://stub/logs",
                output_preview={"records": []},
                side_effect_type=ToolSideEffectType.READ_ONLY,
                started_at=now, ended_at=now, duration_ms=0,
            )
        adapter = XdrOpenApiAdapter(
            xdr_config(),
            session=FakeSession(response=FakeResponse(200, empty_payload)),
            fallback_adapter=FixedSampleAdapter(),
            xdr_log_query_handler=_ok_log_handler,
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-404"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertTrue(
            any("empty_result" in str(e.message) for e in ctx.errors),
            f"errors 中没有 empty_result：{ctx.errors}",
        )

    def test_field_mapping_failure_does_not_fallback(self) -> None:
        """全部条目映射失败且 allow_fallback=false → ValueError 含"字段映射"。"""
        # 直接测 adapter；用 patch 强制 _to_alert_record 全部返回 None，避免 pydantic 实现差异
        import sec_agent.platforms.xdr_openapi as xdr_mod
        item = {
            "uuId": "REAL-XDR-BAD",
            "eventName": "X映射失败样例",
            "severity": "高危",
            "srcIp": "1.1.1.1", "dstIp": "2.2.2.2",
            "firstTime": 1787155200,
        }
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=False, max_pages=1),
            session=FakeSession(response=FakeResponse(200, {"data": {"item": [item]}})),
            fallback_adapter=FixedSampleAdapter(),
        )
        with patch.object(xdr_mod, "_to_alert_record", lambda _i: None):
            with self.assertRaises(ValueError) as cm:
                adapter.fetch_alerts(xdr_event_id="REAL-XDR-BAD")
        self.assertIn("字段映射", str(cm.exception))

    # -------------------------------------------------------------------------- 配置校验
    def test_startup_check_requires_base_url_and_auth_secret(self) -> None:
        with self.assertRaisesRegex(ValueError, "XDR_BASE_URL"):
            XdrOpenApiAdapter(xdr_config(base_url=None))
        # token 模式：缺 token → ValueError 含 XDR_TOKEN
        with self.assertRaisesRegex(ValueError, "XDR_TOKEN"):
            XdrOpenApiAdapter(xdr_config(token=None))

    def test_auth_code_config_validation_rejects_missing_code(self) -> None:
        """auth_type=auth_code 且 XDR_AUTH_CODE 未提供 → ValueError 含 XDR_AUTH_CODE。"""
        with self.assertRaisesRegex(ValueError, "XDR_AUTH_CODE"):
            XdrOpenApiAdapter(
                xdr_config(auth_type="auth_code", token=None, access_key=None, secret_key=None, auth_code=None)
            )
        # 反例：若提供了合法的 ak+sk 且是 aksk 模式，应该不抛（哪怕缺 auth_code）
        XdrOpenApiAdapter(
            xdr_config(auth_type="aksk", token=None, access_key="ak_dummy", secret_key="sk_dummy")
        )

    # -------------------------------------------------------------------------- 官方签名头
    def test_aksk_auth_builds_official_authorization_format(self) -> None:
        """OfficialXdrSigner → algorithm=HMAC-SHA256, Access=..., SignedHeaders=..., Signature=...。"""
        signer = OfficialXdrSigner(ak="UNIT-TEST-AK", sk="UNIT-TEST-SK")
        with patch("sec_agent.platforms.xdr_openapi.datetime") as mock_dt:
            mock_dt.now.return_value = type("Fakedt", (), {})()
            mock_dt.now.return_value.strftime = lambda fmt: "20260819T000000Z"  # 固定 sign-date
            headers = signer.sign_headers(
                method="POST",
                url="https://xdr.example.test/api/xdr/v1/alerts/list",
                headers={"content-type": "application/json", "User-Agent": "spark-sec-agent-be/1.0"},
                query_params={},
                json_body={"page": 1, "pageSize": 50, "startTimestamp": 1787155200},
            )
        self.assertIn("Authorization", headers)
        auth = headers["Authorization"]
        self.assertTrue(auth.startswith("algorithm=HMAC-SHA256,"), f"Authorization 前缀错：{auth}")
        self.assertIn("Access=UNIT-TEST-AK", auth)
        self.assertIn("SignedHeaders=", auth)
        self.assertIn("Signature=", auth)
        # 官方 header 必须存在：sdk-host / sdk-content-type / sign-date
        self.assertIn("sdk-host", headers)
        self.assertIn("sdk-content-type", headers)
        self.assertEqual(headers["sign-date"], "20260819T000000Z")

    def test_aksk_adapter_sends_official_headers_in_request(self) -> None:
        """adapter POST 时：signer 生成的官方头被实际注入请求（用 handler 捕获）。"""
        captured: list[tuple] = []

        def capture_handler(url, headers, body, method):
            captured.append((url, dict(headers), body, method))
            return FakeResponse(200, {"data": {"item": []}}).json()

        cfg = xdr_config(
            auth_type="aksk",
            token=None,
            access_key="TESTAK01",
            secret_key="TESTSK01",
            preflight_http_check=False,
            fetch_alerts_http_handler=capture_handler,
        )
        adapter = XdrOpenApiAdapter(cfg, session=FakeSession(FakeResponse(200, {"data": {"item": []}})))
        try:
            adapter.fetch_alerts()
        except ValueError as exc:  # 空结果抛出是预期的，我们只看捕获的头
            self.assertIn("empty_result", str(exc))

        self.assertTrue(captured, "handler 没被调用")
        headers = captured[0][1]
        self.assertIn("Authorization", headers)
        auth = headers["Authorization"]
        self.assertTrue(auth.startswith("algorithm=HMAC-SHA256,"))
        self.assertIn("Access=TESTAK01", auth)
        self.assertIn("sdk-host", headers)
        self.assertIn("sign-date", headers)

    # -------------------------------------------------------------------------- 分页遍历
    def test_pagination_traverses_pages_and_dedupes_across_pages(self) -> None:
        """3 页，page_size=2，total=6；第 2 页含与第 1 页重复 uuId（更完整），验证去重并保留完整条目。"""
        page1 = {"data": {"total": 6, "item": [
            {"uuId": "A-001", "eventName": "E1", "severity": "高危", "srcIp": "1.1.1.1",
             "dstIp": "2.2.2.2", "firstTime": 1787155200, "riskScoreSeed": 80,
             "traceBackId": "TB-A1"},
            {"uuId": "A-002", "eventName": "E2", "severity": "中危", "srcIp": "3.3.3.3",
             "dstIp": "4.4.4.4", "firstTime": 1787155200, "riskScoreSeed": 50},
        ]}}
        page2 = {"data": {"total": 6, "item": [
            # 重复 A-001，但完整性字段更多：应该保留此条
            {"uuId": "A-001", "eventName": "E1-ext", "severity": "严重", "srcIp": "1.1.1.1",
             "dstIp": "2.2.2.2", "hostIp": "2.2.2.2", "firstTime": 1787155200,
             "attackStage": "S1", "platformConfidence": 88, "riskScoreSeed": 92,
             "branchName": "XDR", "traceBackId": "TB-A1-EXT",
             "evidenceRefs": [{"ref_id": "EV-01"}]},
            {"uuId": "A-003", "eventName": "E3", "severity": "低危", "srcIp": "5.5.5.5",
             "dstIp": "6.6.6.6", "firstTime": 1787155200, "riskScoreSeed": 20},
        ]}}
        page3 = {"data": {"total": 6, "item": [
            {"uuId": "A-004", "eventName": "E4", "severity": "高危", "srcIp": "7.7.7.7",
             "dstIp": "8.8.8.8", "firstTime": 1787155200, "riskScoreSeed": 75},
        ]}}
        responses = [
            FakeResponse(200, page1),
            FakeResponse(200, page2),
            FakeResponse(200, page3),
        ]
        adapter = XdrOpenApiAdapter(
            xdr_config(page_size=2, max_pages=5),
            session=FakeSession(responses=responses),
        )
        alerts = adapter.fetch_alerts()

        by_id = {a.alert_id: a for a in alerts}
        self.assertEqual(set(by_id.keys()), {"A-001", "A-002", "A-003", "A-004"})
        # 重复的 A-001 保留的是完整度更高的 page2 那版：含 attack_stage / S1
        self.assertEqual(by_id["A-001"].scenario_fields.get("attack_stage"), "S1")
        self.assertEqual(by_id["A-001"].raw_severity, "critical")  # page2 severity=严重
        self.assertEqual(by_id["A-001"].scenario_fields.get("risk_score_seed"), 92)

    # -------------------------------------------------------------------------- 定向本地筛选
    def test_directional_lookup_locally_filters_uuid_after_pagination(self) -> None:
        """定向 xdr_event_id=TARGET-X：跨 2 页扫描，第 2 页才命中；断言只返回 1 条且请求参数不带 ID。"""
        page1 = {"data": {"total": 2, "item": [
            {"uuId": "NOPE-1", "eventName": "E1", "severity": "高危", "srcIp": "1.1.1.1",
             "dstIp": "2.2.2.2", "firstTime": 1787155200, "riskScoreSeed": 60},
        ]}}
        page2 = {"data": {"total": 2, "item": [
            {"uuId": "TARGET-X", "eventName": "TARGET-E", "severity": "高危",
             "srcIp": "9.9.9.9", "dstIp": "10.10.10.10", "srcPort": 30000,
             "dstPort": 443, "firstTime": 1787155200, "riskScoreSeed": 88,
             "traceBackId": "TB-TX"},
        ]}}
        sess = FakeSession(responses=[FakeResponse(200, page1), FakeResponse(200, page2)])
        adapter = XdrOpenApiAdapter(xdr_config(page_size=1, max_pages=5), session=sess)
        alerts = adapter.fetch_alerts(xdr_event_id="TARGET-X")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_id, "TARGET-X")
        self.assertEqual(alerts[0].dst_ip, "10.10.10.10")
        # 所有请求都不应当在 body/params 中带 event_id
        for (method, url, kwargs) in sess.calls:
            self.assertNotIn("event_id", kwargs.get("json", {}),
                             f"请求把 xdr_event_id 塞进 body 了：{method} {url}")
            self.assertNotIn("TARGET-X", (kwargs.get("body") or ""),
                             f"请求把 xdr_event_id 塞进序列化 body：{method} {url}")

    def test_directional_lookup_not_found_does_not_fallback_when_disabled(self) -> None:
        """定向筛选 NOT_FOUND 且 allow_fixed_sample_fallback=false → 显式抛 ValueError，不降级。"""
        payload = {"data": {"total": 1, "item": [
            {"uuId": "SOMETHING-ELSE", "eventName": "E", "severity": "中危",
             "srcIp": "1.1.1.1", "dstIp": "2.2.2.2", "firstTime": 1787155200}
        ]}}
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=False),
            session=FakeSession(response=FakeResponse(200, payload)),
            fallback_adapter=FixedSampleAdapter(),
        )
        with self.assertRaises(ValueError) as cm:
            adapter.fetch_alerts(xdr_event_id="MISSING-ID")
        self.assertIn("MISSING-ID", str(cm.exception))
        # 不应出现 fixed_sample_fallback 迹象（不降级）
        self.assertNotIn("降级", str(cm.exception))

    # -------------------------------------------------------------------------- xdr_log_query 工具
    def test_xdr_log_query_uses_openapi_handler_instead_of_builtin_sample(self) -> None:
        """默认 xdr_log_query：真实 POST 到 logs_path，返回的 raw_result_ref 不使用 builtin 前缀。"""
        resp = FakeResponse(200, {"data": {"items": [{"rule_name": "真实XDR日志"}]}})
        sess = FakeSession(response=resp)
        adapter = XdrOpenApiAdapter(xdr_config(logs_path="/openapi/logs"), session=sess)

        result = adapter.run_tool(self._xdr_log_request())

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertTrue(
            result.raw_result_ref.startswith("xdr://openapi/logs/"),
            f"raw_result_ref 应以 xdr://openapi/logs/ 开头，实际 {result.raw_result_ref!r}",
        )
        self.assertFalse(
            "builtin://xdr-log-query" in (result.raw_result_ref or ""),
            f"不应调用内置 sample：raw_result_ref={result.raw_result_ref}",
        )
        self.assertEqual(result.output_preview.get("records"), [{"rule_name": "真实XDR日志"}])
        # 实际请求：POST https://xdr.example.test/openapi/logs
        self.assertTrue(sess.calls, "未发起 HTTP")
        method, url, _kw = sess.calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://xdr.example.test/openapi/logs")

    def test_xdr_log_query_can_use_injected_handler(self) -> None:
        """构造期注入自定义 xdr_log_query_handler → run_tool 使用注入的 handler。"""
        def injected_handler(request: ToolRequest) -> ToolResult:
            now = utc_now()
            return ToolResult(
                call_id=request.call_id,
                trace_id=request.trace_id,
                event_id=request.event_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                idempotency_key=request.idempotency_key,
                status=ToolCallStatus.SUCCESS,
                summary="已调用注入的真实 XDR 查询 handler",
                raw_result_ref="xdr://injected/logs",
                output_preview={"records": [{"source": "injected"}]},
                side_effect_type=ToolSideEffectType.READ_ONLY,
                started_at=now,
                ended_at=now,
                duration_ms=1,
            )

        adapter = XdrOpenApiAdapter(xdr_config(), session=FakeSession(), xdr_log_query_handler=injected_handler)

        result = adapter.run_tool(self._xdr_log_request())

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(result.raw_result_ref, "xdr://injected/logs")
        self.assertEqual(result.output_preview["records"], [{"source": "injected"}])

    # -------------------------------------------------------------------------- PlatformAdapter 三签名
    def test_platform_adapter_three_signatures_work(self) -> None:
        """fetch_alerts / run_tool / query_action_status 都不报错。"""
        payload = _real_xdr_webshell_payload(total=1)
        sess = FakeSession(responses=[
            FakeResponse(200, payload),
            FakeResponse(200, {"data": {"items": []}}),
        ])
        adapter = XdrOpenApiAdapter(xdr_config(), session=sess, fallback_adapter=FixedSampleAdapter())
        # fetch_alerts
        alerts = adapter.fetch_alerts(xdr_event_id="REAL-XDR-WEBSHELL-001")
        self.assertEqual(len(alerts), 1)
        self.assertIsInstance(alerts[0], AlertRecord)
        # run_tool
        tr = adapter.run_tool(self._xdr_log_request())
        self.assertIsInstance(tr, ToolResult)
        # query_action_status（未知键 → 默认值）
        status = adapter.query_action_status("not-exist-key")
        self.assertIsInstance(status, str)

    # -------------------------------------------------------------------------- misc
    def test_strenum_platform_result_code_supports_startswith_for_auth(self) -> None:
        self.assertTrue(str(PlatformResultCode.AUTH_FAILURE).startswith("auth"))

    def _xdr_log_request(self) -> ToolRequest:
        return ToolRequest(
            trace_id="trace-xdr-tool",
            event_id="evt-xdr-tool",
            stage=BusinessStatus.INVESTIGATING,
            tool_name="xdr_log_query",
            action_name="query_xdr_log",
            params={"event_id": "evt-xdr-tool"},
            reason="查询真实 XDR 日志",
            idempotency_key="xdr-log-query-test",
            risk_level=ToolRiskLevel.LOW,
        )


if __name__ == "__main__":
    unittest.main()
