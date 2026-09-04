# -*- coding: utf-8 -*-
"""深信服 MCP 客户端契约测试（任务二：真实平台工具接入准备）。

验证点（对齐 28 日真实平台联调的 dbproxy 工具契约）：
  1. dbproxy 查询成功但无数据（{"code":0,"msg":"","data":[]}）→ status=partial；
  2. dbproxy 查询成功且有数据（data 非空）→ status=success，文本原样；
  3. dbproxy 结构化错误（code != 0，msg 携带错误信息）→ status=failed；
  4. 非 dbproxy 工具明示错误（isError / error JSON / 已知错误前缀）→ failed；
  5. 非 dbproxy 正常研判文本仍按原样 success；
  6. 上述结果经 ToolResult.to_str() 后可被 LLM 消费，区分「空数据」与「失败」，
     从而进入调查证据缺口 / 停止条件（数据为空即触发停止，而非静默成功）。

不依赖真实 MCP 网络：用 FakeMCPClient 按正式契约构造 tools/call 返回。
"""
from __future__ import annotations

import json
import unittest

from sec_agent.deep_agent.tools.mcp_client import (
    MCPTool,
    _extract_text,
    _to_tool_result,
)


class FakeMCPClient:
    """按 MCP tools/call 正式契约返回固定结果的假客户端。"""

    def __init__(self, result):
        self._result = result

    def call_tool(self, name, arguments):
        return self._result


def _content_result(text: str) -> dict:
    """MCP tools/call 常见返回：content 列表内嵌 text。"""
    return {"content": [{"type": "text", "text": text}]}


def _structured_result(payload: dict) -> dict:
    """MCP tools/call 另一种返回：structuredContent。"""
    return {"structuredContent": payload}


class TestExtractText(unittest.TestCase):
    def test_content_list(self):
        self.assertEqual(_extract_text(_content_result("hello")), "hello")

    def test_structured_content(self):
        payload = {"code": 0, "msg": "", "data": []}
        self.assertEqual(_extract_text(_structured_result(payload)), json.dumps(payload, ensure_ascii=False))

    def test_plain_string(self):
        self.assertEqual(_extract_text("raw text"), "raw text")


class TestDbproxyContract(unittest.TestCase):
    """dbproxy 系列工具契约：code/data 结构。"""

    def test_empty_data_is_partial(self):
        result = _to_tool_result(_content_result('{"code":0,"msg":"","data":[]}'))
        self.assertEqual(result.status, "partial")
        self.assertIn("无数据", result.summary)
        self.assertEqual(result.data, [])
        # partial 不被误报为失败，to_str 能明确区分
        self.assertIn("部分成功", result.to_str())

    def test_empty_data_null_is_partial(self):
        result = _to_tool_result(_content_result('{"code":0,"msg":"","data":null}'))
        self.assertEqual(result.status, "partial")

    def test_non_empty_data_is_success(self):
        payload = '{"code":0,"msg":"","data":[{"name":"shell.php","severity":"high"}]}'
        result = _to_tool_result(_content_result(payload))
        self.assertEqual(result.status, "success")
        self.assertIn("shell.php", result.summary)

    def test_business_error_is_failed(self):
        result = _to_tool_result(_content_result('{"code":1001,"msg":"参数不合法","data":null}'))
        self.assertEqual(result.status, "failed")
        self.assertIn("参数不合法", result.error)
        self.assertIn("失败", result.to_str())

    def test_code_zero_string_treated_as_success_code(self):
        result = _to_tool_result(_content_result('{"code":"0","msg":"","data":[]}'))
        self.assertEqual(result.status, "partial")

    def test_empty_error_field_does_not_override_dbproxy_status(self):
        result = _to_tool_result(_content_result('{"code":0,"data":[],"error":""}'))
        self.assertEqual(result.status, "partial")


class TestNonDbproxyTool(unittest.TestCase):
    """非 dbproxy 工具按明示错误信号区分 failed 与正常研判文本。"""

    def test_secgpt_like_text_is_success(self):
        result = _to_tool_result(_content_result("[安全GPT研判] 疑似真实 WebShell 攻击"))
        self.assertEqual(result.status, "success")
        self.assertIn("WebShell", result.summary)

    def test_no_code_field_is_success(self):
        result = _to_tool_result(_content_result('{"answer":"ok","score":0.9}'))
        self.assertEqual(result.status, "success")

    def test_empty_text_is_partial(self):
        # XDR「网络安全数据查询」的 vul_资产关联漏洞数据查询 命中不到数据时
        # content[0].text 为空串（isError 仍为 false），应识别为“成功但无数据”，
        # 而不是 success + 空摘要，避免 Agent 把“无数据”误当“出错”。
        result = _to_tool_result(_content_result(""))
        self.assertEqual(result.status, "partial")
        self.assertIn("无数据", result.summary)
        self.assertIn("部分成功", result.to_str())

    def test_is_error_flag_is_failed(self):
        result = _to_tool_result({
            "isError": True,
            "content": [{"type": "text", "text": "tool rejected request"}],
        })
        self.assertEqual(result.status, "failed")
        self.assertIn("rejected", result.error)

    def test_error_object_is_failed(self):
        result = _to_tool_result(_content_result('{"error":{"code":500,"message":"gateway failed"}}'))
        self.assertEqual(result.status, "failed")
        self.assertIn("gateway failed", result.error)

    def test_known_error_text_is_failed(self):
        messages = (
            "Input validation error: field params is required",
            "Cannot do exclusion on field logTraceInfo",
            "HTTP 500: upstream secgpt unavailable",
        )
        for message in messages:
            with self.subTest(message=message):
                result = _to_tool_result(_content_result(message))
                self.assertEqual(result.status, "failed")

    def test_error_words_inside_analysis_remain_success(self):
        text = "研判说明：上游曾出现 HTTP 500，但本次返回了有效分析。"
        result = _to_tool_result(_content_result(text))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.summary, text)


class TestMCPToolEndToEnd(unittest.TestCase):
    """MCPTool.call 端到端：按契约返回后，调查 Agent 能正常消费。"""

    def _tool(self, result) -> MCPTool:
        return MCPTool(FakeMCPClient(result), "dbproxy_告警数据查询工具", "查询告警", {"type": "object", "properties": {}})

    def test_call_empty_data_partial(self):
        tool = self._tool(_content_result('{"code":0,"msg":"","data":[]}'))
        result = tool.call({"query": {"bool": {"must": [{"term": {"hostIp": "192.168.1.100"}}]}}})
        self.assertEqual(result.status, "partial")

    def test_call_non_empty_data_success(self):
        tool = self._tool(_content_result('{"code":0,"msg":"","data":[{"name":"xdr-alert-001"}]}'))
        result = tool.call({})
        self.assertEqual(result.status, "success")


if __name__ == "__main__":
    unittest.main(verbosity=2)
