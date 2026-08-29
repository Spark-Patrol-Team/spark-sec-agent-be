import unittest
import json
import hmac
import hashlib
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

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if self.exc:
            raise self.exc
        return self.response

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.exc:
            raise self.exc
        return self.response


def xdr_config(**overrides) -> XdrOpenApiConfig:
    values = {
        "base_url": "https://xdr.example.test",
        "auth_type": "auth_code",
        "auth_code": "unit-test-auth-code",
        "alerts_path": "/api/xdr/v1/alerts/list",
        "startup_check": True,
        "preflight_http_check": False,
    }
    values.update(overrides)
    return XdrOpenApiConfig(**values)


class XdrOpenApiPlatformTest(unittest.TestCase):
    def test_real_xdr_alert_mapping_alignment(self) -> None:
        """验证 8/29 真实响应结构（uuId, lastTime, item）的精准映射"""
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
                                "uuId": "alert-9fd0c034-ba09-4311-8360-cf1787206450",
                                "name": "SQL server数据库查询sa账户密码攻击",
                                "severity": 70,
                                "gptResultDescription": "真实攻击成功",
                                "srcIp": ["192.168.100.100"],
                                "hostIp": "192.168.100.200",
                                "lastTime": 1787155200,
                                "devSourceName": ["XDR"]
                            }
                        ]
                    }
                },
            )
        )
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="alert-9fd0c034-ba09-4311-8360-cf1787206450"))

        # 验证主链状态
        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(ctx.effective_source, "xdr_openapi")
        
        # 验证字段映射
        event = ctx.event_summary
        self.assertEqual(event.alert_refs, ["alert-9fd0c034-ba09-4311-8360-cf1787206450"])
        self.assertIn("192.168.100.200", event.entities.get("assets", []))
        self.assertEqual(ctx.triage.risk_score, 80)  # 70 -> 高危 -> 种子 80
        
        # 验证请求参数
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://xdr.example.test/api/xdr/v1/alerts/list")
        self.assertEqual(kwargs["json"]["page"], 1)

    def test_auth_code_signature_logic(self) -> None:
        """验证 8/29 要求的 HMAC-SHA256(auth_code, method + path + timestamp + nonce + body) 签名逻辑"""
        adapter = XdrOpenApiAdapter(xdr_config(auth_code="test-code"), session=FakeSession())
        
        with patch("sec_agent.platforms.xdr_openapi.time.time", return_value=1000), \
             patch("uuid.uuid4", return_value="test-nonce"):
            
            path = "/api/xdr/v1/alerts/list"
            params = {"page": 1}
            headers = adapter._headers("POST", path, params)
            
            # 手动计算预期签名
            body_str = json.dumps(params, separators=(',', ':'))
            string_to_sign = f"POST{path}1000test-nonce{body_str}"
            expected_sig = hmac.new(b"test-code", string_to_sign.encode(), hashlib.sha256).hexdigest()
            
            self.assertEqual(headers["x-auth-code"], "test-code")
            self.assertEqual(headers["x-timestamp"], "1000")
            self.assertEqual(headers["x-nonce"], "test-nonce")
            self.assertEqual(headers["x-signature"], expected_sig)

    def test_empty_result_handling(self) -> None:
        """验证真实空结果（item 为空列表）的处理"""
        session = FakeSession(FakeResponse(200, {"code": "Success", "data": {"item": []}}))
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="NON-EXISTENT"))

        self.assertEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("empty_result", ctx.errors[0].message)

    def test_field_mapping_robustness(self) -> None:
        """验证字段缺失时的回退逻辑"""
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "data": {
                        "item": [
                            {
                                "uuId": "MISSING-FIELDS",
                                "name": "测试告警",
                                "lastTime": 1787155200,
                                # 缺失 hostIp, 使用 dstIp
                                "dstIp": ["10.0.0.1"]
                            }
                        ]
                    }
                }
            )
        )
        adapter = XdrOpenApiAdapter(xdr_config(), session=session)
        orchestrator = Orchestrator(platform=adapter, store=InMemoryEventRepository())

        ctx = orchestrator.start(StartRunRequest(source="xdr", xdr_event_id="MISSING-FIELDS"))
        
        # 只要不是 FAILED，说明接入和映射已成功
        self.assertNotEqual(ctx.status, BusinessStatus.FAILED)
        self.assertIn("10.0.0.1", ctx.event_summary.entities.get("assets", []))


if __name__ == "__main__":
    unittest.main()
