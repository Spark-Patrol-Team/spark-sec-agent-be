import unittest
from unittest.mock import patch

import requests

from sec_agent.domain.models import (
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
from sec_agent.platforms.xdr_openapi import XdrOpenApiAdapter, XdrOpenApiConfig
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.orchestrator import Orchestrator


class FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.exc:
            raise self.exc
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if self.exc:
            raise self.exc
        return self.response


def xdr_config(**overrides) -> XdrOpenApiConfig:
    values = {
        "base_url": "https://xdr.example.test",
        "token": "unit-test-token",
        "startup_check": True,
        "preflight_http_check": False,
    }
    values.update(overrides)
    return XdrOpenApiConfig(**values)


class XdrOpenApiPlatformTest(unittest.TestCase):
    def test_real_xdr_alert_continues_existing_main_chain(self) -> None:
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "event_id": "REAL-XDR-WEBSHELL-001",
                            "event_time": "2026-08-28T09:30:00+08:00",
                            "source_device_type": "XDR",
                            "source_device_name": "XDR",
                            "event_type": "webshell",
                            "rule_or_event_name": "WebShell蚁剑工具文件管理",
                            "severity": "critical",
                            "source_ip": "198.51.100.33",
                            "destination_ip": "198.51.100.11",
                            "affected_asset": "198.51.100.11",
                            "evidence_source": "xdr_security_alert",
                            "evidence_refs": ["alert_time", "alert_name", "destination_ip"],
                            "sample_nature": "platform_derived",
                            "status": "new",
                            "risk_score_seed": 95,
                            "recommended_action": "人工审批后隔离受影响主机。",
                        }
                    ]
                },
            )
        )
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-WEBSHELL-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.source, "xdr")
        self.assertEqual(ctx.requested_source, "xdr")
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        self.assertIsNone(ctx.fallback_source)
        self.assertEqual(ctx.alert_refs, ["REAL-XDR-WEBSHELL-001"])
        self.assertEqual(ctx.triage.risk_score, 95)
        self.assertEqual(ctx.response.plan.target, "198.51.100.11")
        self.assertTrue(session.calls)
        self.assertEqual(session.calls[0][0], "POST")
        self.assertEqual(session.calls[0][1], "https://xdr.example.test/api/xdr/v1/alerts/list")
        self.assertEqual(session.calls[0][2]["json"], {"page": 1, "pageSize": 10})

    def test_auth_failure_fails_without_fixed_sample_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(FakeResponse(401, {"message": "unauthorized"})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-001"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertTrue(ctx.trace_id.startswith("trace-"))
        self.assertIn("auth", ctx.errors[0].message)

    def test_timeout_can_fallback_to_fixed_sample_when_enabled(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(exc=requests.Timeout("read timeout")),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.source, "xdr")
        self.assertEqual(ctx.requested_source, "xdr")
        self.assertEqual(ctx.effective_source, "fixed_sample_fallback")
        self.assertEqual(ctx.fallback_source, "fixed_sample")
        self.assertIn("已降级到固定样例", ctx.timeline[0].message)
        self.assertIn("timeout", ctx.errors[0].message)

    def test_empty_result_fails_without_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(),
            session=FakeSession(FakeResponse(200, {"data": []})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-404"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("empty_result", ctx.errors[0].message)

    def test_field_mapping_failure_does_not_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(FakeResponse(200, {"data": [{"event_id": "REAL-XDR-BAD"}]})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-BAD"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("field_mapping", ctx.errors[0].message)

    def test_startup_check_requires_base_url_and_auth_secret(self) -> None:
        with self.assertRaisesRegex(ValueError, "XDR_BASE_URL"):
            XdrOpenApiAdapter(xdr_config(base_url=None))

        with self.assertRaisesRegex(ValueError, "XDR_TOKEN"):
            XdrOpenApiAdapter(xdr_config(token=None))

    def test_aksk_auth_builds_hmac_headers(self) -> None:
        session = FakeSession(FakeResponse(200, {"data": []}))
        adapter = XdrOpenApiAdapter(
            xdr_config(
                auth_type="aksk",
                token=None,
                access_key="ak",
                secret_key="sk",
            ),
            session=session,
        )

        with patch("sec_agent.platforms.xdr_openapi.time.time", return_value=1000), patch(
            "sec_agent.platforms.xdr_openapi.secrets.token_hex", return_value="nonce"
        ):
            headers = adapter._headers("GET", "/api/v1/alerts", {"event_id": "E 1", "limit": 1})

        self.assertEqual(headers["X-XDR-Access-Key"], "ak")
        self.assertEqual(headers["X-XDR-Timestamp"], "1000")
        self.assertEqual(headers["X-XDR-Nonce"], "nonce")
        self.assertEqual(headers["X-XDR-Signature-Method"], "HMAC-SHA256")
        self.assertEqual(headers["X-XDR-Signature"], "dhL2YPIT/XSJ8XCeIlKf5qHUV9jNmGpbK288cpfvIpI=")
        self.assertNotIn("Authorization", headers)

    def test_xdr_log_query_uses_openapi_handler_instead_of_builtin_sample(self) -> None:
        session = FakeSession(FakeResponse(200, {"data": {"items": [{"rule_name": "真实XDR日志"}]}}))
        adapter = XdrOpenApiAdapter(xdr_config(logs_path="/openapi/logs"), session=session)

        result = adapter.run_tool(self._xdr_log_request())

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(result.raw_result_ref, f"xdr://openapi/logs/{result.call_id}")
        self.assertNotIn("builtin://xdr-log-query", result.raw_result_ref)
        self.assertEqual(result.output_preview["records"], [{"rule_name": "真实XDR日志"}])
        self.assertEqual(session.calls[0][1], "https://xdr.example.test/openapi/logs")

    def test_xdr_log_query_can_use_injected_handler(self) -> None:
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

    def test_real_xdr_list_alert_response_maps_and_flows(self) -> None:
        """陈敏 8/28 交付的真实 XDR 列表响应（脱敏）应能映射并通过主链压成 1 个事件。"""
        payload = {
            "code": 200,
            "message": "success",
            "data": {
                "total": 1,
                "item": [
                    {
                        "uuId": "alert-20260828-0001",
                        "name": "WebShell 攻击行为 (AntSword)",
                        "firstTime": 1724810000,
                        "lastTime": 1724810900,
                        "hostIp": "198.51.100.10",
                        "srcIp": "203.0.113.5",
                        "severity": "high",
                        "confidence": 95,
                        "gpt_result_desc": "检测到明显的蚁剑 WebShell 连接特征，攻击者正在尝试执行系统命令。",
                        "ruleName": "WebShell_Detection_Rule",
                        "attackStage": "Lateral Movement",
                    }
                ],
            },
        }
        session = FakeSession(FakeResponse(200, payload))
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="alert-20260828-0001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        self.assertEqual(ctx.alert_refs, ["alert-20260828-0001"])
        self.assertEqual(ctx.triage.risk_score, 80)
        self.assertEqual(ctx.triage.verdict, "malicious")
        self.assertEqual(ctx.triage.confidence, 0.85)
        self.assertEqual(ctx.triage.priority, "high")
        self.assertTrue(ctx.triage.should_investigate)

        records = adapter.fetch_alerts(xdr_event_id="alert-20260828-0001")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.alert_id, "alert-20260828-0001")
        self.assertEqual(record.name, "WebShell 攻击行为 (AntSword)")
        self.assertEqual(record.alert_type, "webshell")
        self.assertEqual(record.raw_severity, "high")
        self.assertEqual(record.src_ip, "203.0.113.5")
        self.assertEqual(record.dst_ip, "198.51.100.10")
        self.assertEqual(record.assets, ["198.51.100.10"])
        self.assertEqual(record.scenario_fields.get("confidence"), 95)
        self.assertEqual(record.scenario_fields.get("stage"), "Lateral Movement")
        self.assertIn("gpt_result_desc", record.scenario_fields)
        self.assertTrue(session.calls)
        self.assertEqual(session.calls[0][0], "POST")
        self.assertEqual(session.calls[0][1], "https://xdr.example.test/api/xdr/v1/alerts/list")
        self.assertEqual(session.calls[0][2]["json"], {"page": 1, "pageSize": 10})

    def test_real_xdr_aksk_list_contract_sql_alert_flows_to_approval(self) -> None:
        """真实 XDR OpenAPI(doc: 8/29) AK/SK 联动码签名 + POST /api/xdr/v1/alerts/list。
        响应外层 {code,message,data:{total,page,pageSize,item}}，告警唯一标识为 uuId。
        以李雨妍建议的 alert-9fd0c034-…（SQL server sa 账户密码攻击，高危/待处置）验证主链。
        """
        payload = {
            "code": "Success",
            "message": "成功",
            "data": {
                "total": 8,
                "page": 1,
                "pageSize": 10,
                "item": [
                    {
                        "uuId": "alert-9fd0c034-ba09-4311-8360-cf1787206450",
                        "name": "SQL server数据库查询sa账户密码攻击",
                        "firstTime": 1785110400,
                        "severity": "高危",
                        "srcIp": "192.168.100.100",
                        "dstIp": "192.168.100.200",
                        "hostIp": "192.168.100.200",
                        "gpt_result_desc": "真实攻击成功",
                        "attackStatus": "待处置",
                        "ruleName": "SQLServer_Sa_Password_Attack",
                        "attackStage": "Lateral Movement",
                    }
                ],
            },
        }
        session = FakeSession(FakeResponse(200, payload))
        adapter = XdrOpenApiAdapter(
            xdr_config(auth_type="aksk", token=None, access_key="ak", secret_key="sk"),
            session=session,
        )
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(
            StartRunRequest(
                source="xdr",
                xdr_event_id="alert-9fd0c034-ba09-4311-8360-cf1787206450",
            )
        )

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.source, "xdr")
        self.assertEqual(ctx.requested_source, "xdr")
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        self.assertIsNone(ctx.fallback_source)
        self.assertEqual(ctx.alert_refs, ["alert-9fd0c034-ba09-4311-8360-cf1787206450"])
        self.assertEqual(ctx.errors, [])
        self.assertEqual(ctx.triage.risk_score, 80)
        self.assertEqual(ctx.triage.verdict, "malicious")
        self.assertEqual(ctx.triage.confidence, 0.85)
        self.assertEqual(ctx.triage.priority, "high")
        self.assertTrue(ctx.triage.should_investigate)
        self.assertEqual(ctx.response.plan.target, "192.168.100.200")

        self.assertEqual(session.calls[0][0], "POST")
        self.assertEqual(session.calls[0][1], "https://xdr.example.test/api/xdr/v1/alerts/list")
        self.assertEqual(session.calls[0][2]["json"], {"page": 1, "pageSize": 10})
        self.assertIn("X-XDR-Access-Key", session.calls[0][2]["headers"])
        self.assertIn("X-XDR-Signature", session.calls[0][2]["headers"])

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
