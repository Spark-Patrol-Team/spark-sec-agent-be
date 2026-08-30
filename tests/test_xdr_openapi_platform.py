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
from sec_agent.platforms.xdr_openapi import XdrOfficialSigner, XdrOpenApiAdapter, XdrOpenApiConfig
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.orchestrator import Orchestrator


class FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(
        self,
        response: FakeResponse | None = None,
        exc: Exception | None = None,
        responses: list[FakeResponse] | None = None,
    ) -> None:
        self.response = response
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        return self.response

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        if self.responses:
            return self.responses.pop(0)
        return self.response

    def send(self, prepared_request, **kwargs):
        self.calls.append((prepared_request.url, {"prepared": prepared_request, **kwargs}))
        if self.exc:
            raise self.exc
        if self.responses:
            return self.responses.pop(0)
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
                    "code": "Success",
                    "message": "成功",
                    "data": {
                        "total": 1,
                        "page": 1,
                        "pageSize": 50,
                        "item": [
                            {
                                "uuId": "REAL-XDR-WEBSHELL-001",
                                "firstTime": "2026-08-28T09:30:00+08:00",
                                "name": "WebShell蚁剑工具文件管理",
                                "severity": "高危",
                                "source_ip": "198.51.100.33",
                                "destination_ip": "198.51.100.11",
                            }
                        ],
                    },
                },
            )
        )
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

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
        prepared = session.calls[0][1]["prepared"]
        self.assertEqual(prepared.body, '{"page": 1, "pageSize": 50}')
        self.assertEqual(prepared.headers["Authorization"], "Bearer unit-test-token")

    def test_auth_failure_fails_without_fixed_sample_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(FakeResponse(401, {"message": "unauthorized"})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

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
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

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
            xdr_config(alerts_path="/api/xdr/v1/alerts/list"),
            session=FakeSession(FakeResponse(200, {"code": "Success", "message": "成功", "data": {"item": []}})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-404"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("empty_result", ctx.errors[0].message)

    def test_field_mapping_failure_does_not_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(allow_fixed_sample_fallback=True),
            session=FakeSession(
                FakeResponse(
                    200,
                    {"code": "Success", "message": "成功", "data": {"item": [{"uuId": "REAL-XDR-BAD"}]}},
                )
            ),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-BAD"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("field_mapping", ctx.errors[0].message)

    def test_startup_check_requires_base_url_and_auth_secret(self) -> None:
        with self.assertRaisesRegex(ValueError, "XDR_BASE_URL"):
            XdrOpenApiAdapter(xdr_config(base_url=None))

        with self.assertRaisesRegex(ValueError, "XDR_TOKEN"):
            XdrOpenApiAdapter(xdr_config(token=None))

    def test_aksk_auth_builds_official_authorization_header_with_post_body(self) -> None:
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

        headers = adapter._headers(
            "POST",
            "/api/xdr/v1/alerts/list",
            body={"page": 1, "pageSize": 10},
        )

        self.assertIn("Authorization", headers)
        self.assertIn("algorithm=HMAC-SHA256", headers["Authorization"])
        self.assertIn("Access=ak", headers["Authorization"])
        self.assertIn("SignedHeaders=content-type;sdk-content-type;sdk-host;sign-date", headers["Authorization"])
        self.assertNotIn("X-XDR-Access-Key", headers)

    def test_official_signer_matches_fixed_signature_fixture(self) -> None:
        request = requests.Request(
            "POST",
            "https://xdr.example.test:1443/api/xdr/v1/alerts/list",
            headers={
                "content-type": "application/json",
                "sign-date": "20260830T000000Z",
            },
            data='{"page": 1, "pageSize": 50, "startTimestamp": 1787155200}',
        )

        XdrOfficialSigner(access_key="ak", secret_key="sk").sign(request)

        self.assertEqual(
            request.headers["Authorization"],
            "algorithm=HMAC-SHA256, Access=ak, SignedHeaders=content-type;sdk-content-type;sdk-host;sign-date, "
            "Signature=ECEAEDF531466425D87A07870821760696CD78E626366E296A0E9DBFCDE60E5E",
        )

    def test_auth_code_requires_auth_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "XDR_AUTH_CODE"):
            XdrOpenApiAdapter(
                xdr_config(
                    auth_type="auth_code",
                    token=None,
                    access_key=None,
                    secret_key=None,
                    auth_code=None,
                )
            )

    def test_fetch_alerts_walks_pages_and_filters_by_uuid_locally(self) -> None:
        session = FakeSession(
            responses=[
                FakeResponse(
                    200,
                    {
                        "code": "Success",
                        "message": "成功",
                        "data": {
                            "total": 11,
                            "page": 1,
                            "pageSize": 10,
                            "item": [
                                {
                                    "uuId": f"REAL-XDR-SQLI-{index:03d}",
                                    "firstTime": "2026-08-28T09:30:00+08:00",
                                    "name": "通用SQL注入攻击",
                                    "severity": "高危",
                                    "source_ip": "198.51.100.33",
                                    "destination_ip": "198.51.100.11",
                                }
                                for index in range(10)
                            ],
                        },
                    },
                ),
                FakeResponse(
                    200,
                    {
                        "code": "Success",
                        "message": "成功",
                        "data": {
                            "total": 11,
                            "page": 2,
                            "pageSize": 10,
                            "item": [
                                {
                                    "uuId": "REAL-XDR-SQLI-TARGET",
                                    "firstTime": "2026-08-28T09:45:00+08:00",
                                    "name": "通用SQL注入攻击",
                                    "severity": "高危",
                                    "source_ip": "198.51.100.44",
                                    "destination_ip": "198.51.100.22",
                                }
                            ],
                        },
                    },
                ),
            ]
        )
        adapter = XdrOpenApiAdapter(
            xdr_config(alerts_path="/api/xdr/v1/alerts/list", alert_page_size=10),
            session=session,
        )

        alerts = adapter.fetch_alerts(xdr_event_id="REAL-XDR-SQLI-TARGET")

        self.assertEqual([alert.alert_id for alert in alerts], ["REAL-XDR-SQLI-TARGET"])
        self.assertEqual(alerts[0].alert_type, "sql_injection")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual([call[1]["prepared"].body for call in session.calls], ['{"page": 1, "pageSize": 10}', '{"page": 2, "pageSize": 10}'])

    def test_fetch_alerts_uses_configured_page_size_and_start_timestamp(self) -> None:
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "code": "Success",
                    "message": "成功",
                    "data": {
                        "total": 1,
                        "page": 1,
                        "pageSize": 20,
                        "item": [
                            {
                                "uuId": "REAL-XDR-SQLI-TIME",
                                "firstTime": "2026-08-28T09:45:00+08:00",
                                "name": "通用SQL注入攻击",
                                "severity": "高危",
                                "source_ip": "198.51.100.44",
                                "destination_ip": "198.51.100.22",
                            }
                        ],
                    },
                },
            )
        )
        adapter = XdrOpenApiAdapter(
            xdr_config(alert_page_size=20, alert_start_timestamp=1787880600000),
            session=session,
        )

        alerts = adapter.fetch_alerts()

        self.assertEqual([alert.alert_id for alert in alerts], ["REAL-XDR-SQLI-TIME"])
        self.assertEqual(
            session.calls[0][1]["prepared"].body,
            '{"page": 1, "pageSize": 20, "startTimestamp": 1787880600000}',
        )

    def test_xdr_mapping_accepts_camel_case_and_array_fields(self) -> None:
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "code": "Success",
                    "message": "成功",
                    "data": {
                        "total": 1,
                        "page": 1,
                        "pageSize": 10,
                        "item": [
                            {
                                "uuId": "REAL-XDR-SQLI-ARRAY",
                                "firstTime": 1787880600000,
                                "name": "通用SQL注入攻击",
                                "severity": "高危",
                                "srcIps": ["198.51.100.33"],
                                "srcPorts": [54321],
                                "dstIps": ["198.51.100.11"],
                                "dstPorts": [443],
                            }
                        ],
                    },
                },
            )
        )
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)

        alerts = adapter.fetch_alerts(xdr_event_id="REAL-XDR-SQLI-ARRAY")

        self.assertEqual(alerts[0].src_ip, "198.51.100.33")
        self.assertEqual(alerts[0].src_port, 54321)
        self.assertEqual(alerts[0].dst_ip, "198.51.100.11")
        self.assertEqual(alerts[0].dst_port, 443)

    def test_updated_real_xdr_shape_reaches_approval_and_keeps_raw_context(self) -> None:
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "code": "Success",
                    "message": "成功",
                    "data": {
                        "total": 8,
                        "page": 1,
                        "pageSize": 50,
                        "item": [
                            {
                                "uuId": "alert-unit-test-stable-id",
                                "traceBackId": ["trace-unit-001", "trace-unit-002"],
                                "name": "SQL server数据库查询sa账户密码攻击",
                                "description": "脱敏后的数据库攻击告警描述",
                                "severity": 70,
                                "logCount": 2,
                                "stage": 30,
                                "riskTag": ["异常操作"],
                                "threatClassDesc": "数据库攻击利用",
                                "threatTypeDesc": "异常操作",
                                "threatSubTypeDesc": "异常操作",
                                "attckTechnique": ["TA0001.T1190"],
                                "srcIp": ["198.51.100.100"],
                                "srcPort": [54321],
                                "dstIp": ["198.51.100.200"],
                                "dstPort": [1433],
                                "hostIp": "198.51.100.200",
                                "url": [],
                                "respStatus": 200,
                                "devUidDesc": ["NDR"],
                                "engineName": ["PVS引擎"],
                                "devSourceName": ["XDR"],
                                "gptResult": 110,
                                "gptResultDescription": "真实攻击成功",
                                "attackState": 2,
                                "confidence": 20,
                                "alertDealStatus": 1,
                                "alertDealAction": "待处置",
                                "whiteStatus": "未加白",
                                "firstTime": 1787155200,
                                "lastTime": 1787155260,
                                "updateTime": 1787155265,
                            }
                        ],
                    },
                },
            )
        )
        adapter = XdrOpenApiAdapter(
            xdr_config(alert_start_timestamp=1787155200),
            session=session,
        )
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="alert-unit-test-stable-id"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.alert_refs, ["alert-unit-test-stable-id"])
        self.assertEqual(ctx.triage.risk_score, 80)
        self.assertEqual(ctx.response.plan.target, "198.51.100.200")
        alert_context = ctx.investigation.steps[0].tool_request.params["entities"]
        self.assertEqual(alert_context["dst_ips"], ["198.51.100.200"])
        self.assertIn("alert-unit-test-stable-id:traceBackId:trace-unit-001", ctx.triage.supporting_evidence_refs)

    def test_business_error_fails_without_fallback(self) -> None:
        adapter = XdrOpenApiAdapter(
            xdr_config(),
            session=FakeSession(FakeResponse(200, {"code": "Failed", "message": "签名错误", "data": None})),
            fallback_adapter=FixedSampleAdapter(),
        )
        orchestrator = Orchestrator(
            platform=adapter,
            store=InMemoryEventRepository(),
            investigation_backend="tool_mock",
        )

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="REAL-XDR-001"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("platform_error", ctx.errors[0].message)

    def test_xdr_log_query_uses_openapi_handler_instead_of_builtin_sample(self) -> None:
        session = FakeSession(FakeResponse(200, {"data": {"items": [{"rule_name": "真实XDR日志"}]}}))
        adapter = XdrOpenApiAdapter(xdr_config(logs_path="/openapi/logs"), session=session)

        result = adapter.run_tool(self._xdr_log_request())

        self.assertEqual(result.status, ToolCallStatus.SUCCESS)
        self.assertEqual(result.raw_result_ref, f"xdr://openapi/logs/{result.call_id}")
        self.assertNotIn("builtin://xdr-log-query", result.raw_result_ref)
        self.assertEqual(result.output_preview["records"], [{"rule_name": "真实XDR日志"}])
        self.assertEqual(session.calls[0][0], "https://xdr.example.test/openapi/logs?event_id=evt-xdr-tool")

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
