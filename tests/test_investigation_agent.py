# -*- coding: utf-8 -*-
"""深度调查 Agent 测试。

运行（在项目根目录，需 src 在导入路径上）：
  PYTHONPATH=src python -m unittest tests.test_investigation_agent -v

说明：单元测试不依赖 LLM；集成测试需要配置 LLM_API_KEY 后才会执行。
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from sec_agent.deep_agent.models import SecurityEventInput, InvestigationReport
from sec_agent.deep_agent.tools.mock import build_mock_tools
from sec_agent.deep_agent.tools.base import ALIAS_MAP, Tool, ToolRegistry, ToolResult
from sec_agent.deep_agent.agent import DeepInvestigationAgent
from sec_agent.deep_agent.config import AgentConfig, load_config
from sec_agent.deep_agent.llm import LLMClient
from sec_agent.deep_agent.main import timestamped_output_path

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "investigation" / "sample_event.json"


def _make_tool(name: str, description: str = "测试工具") -> Tool:
    """构造一个可调用的最小工具（别名机制测试用）。"""
    class _T(Tool):
        def call(self, params):
            return ToolResult(summary=f"called:{self.name}")
    _T.name = name
    _T.description = description
    _T.parameters = {"type": "object", "properties": {}}
    return _T()


class TestReportOutputPath(unittest.TestCase):
    def test_timestamp_inserted_before_extension(self):
        p = timestamped_output_path("report.json")
        self.assertEqual(p.suffix, ".json")
        self.assertRegex(p.stem, r"^report_\d{8}_\d{6}$")

    def test_preserves_parent_dir_and_nested_stem(self):
        p = timestamped_output_path("reports/foo.json")
        self.assertEqual(str(p.parent), "reports")
        self.assertRegex(p.stem, r"^foo_\d{8}_\d{6}$")

    def test_no_extension_still_timestamped(self):
        p = timestamped_output_path("report")
        self.assertEqual(p.suffix, "")
        self.assertRegex(p.stem, r"^report_\d{8}_\d{6}$")


class TestModels(unittest.TestCase):
    def test_event_roundtrip(self):
        with open(SAMPLE, encoding="utf-8") as f:
            d = json.load(f)
        ev = SecurityEventInput.from_dict(d)
        self.assertEqual(ev.event_id, "EVENT-001")
        self.assertEqual(ev.target_ip, "192.168.1.100")
        self.assertIsInstance(ev.alerts, list)
        d2 = ev.to_dict()
        self.assertEqual(d2["event_id"], ev.event_id)

    def test_report_serializable(self):
        r = InvestigationReport(conclusion="测试结论", confidence=0.88)
        s = json.dumps(r.to_dict(), ensure_ascii=False)
        self.assertIn("conclusion", s)


class TestMockTools(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        for t in build_mock_tools():
            self.reg.register(t)

    def test_asset_query_hit(self):
        r = self.reg.call("query_asset", {"ip": "192.168.1.100"})
        self.assertEqual(r.status, "success")
        self.assertIn("OA服务器", r.summary)

    def test_asset_query_miss(self):
        r = self.reg.call("query_asset", {"ip": "1.2.3.4"})
        self.assertEqual(r.status, "failed")

    def test_unknown_tool(self):
        r = self.reg.call("no_such_tool", {})
        self.assertEqual(r.status, "failed")

    def test_mock_tools_registered(self):
        self.assertGreaterEqual(len(self.reg.names()), 6)


class TestToolAlias(unittest.TestCase):
    """内部别名：含中文名的 MCP 工具在发给 LLM 前映射为 ASCII，调用时还原。"""

    def test_ascii_tool_keeps_name(self):
        reg = ToolRegistry()
        reg.register(_make_tool("query_asset"))
        self.assertEqual(reg.schemas()[0]["function"]["name"], "query_asset")
        self.assertEqual(reg.resolve("query_asset"), "query_asset")

    def test_chinese_tool_aliased_and_resolved(self):
        reg = ToolRegistry()
        real = "cybersec_攻击状态检测"
        reg.register(_make_tool(real))
        schema_name = reg.schemas()[0]["function"]["name"]
        # schema 名必须符合 OpenAI 函数名模式
        self.assertRegex(schema_name, r"^[a-zA-Z0-9_-]+$")
        self.assertNotEqual(schema_name, real)
        # 别名能解析回真实名，且用别名调用能真正执行到对应工具
        self.assertEqual(reg.resolve(schema_name), real)
        self.assertEqual(reg.call(schema_name, {}).summary, f"called:{real}")

    def test_unknown_tool_still_fails(self):
        reg = ToolRegistry()
        reg.register(_make_tool("query_asset"))
        self.assertEqual(reg.call("no_such_tool", {}).status, "failed")

    def test_alias_map_consistency(self):
        # 收录的别名必须匹配 OpenAI 函数名模式且互不冲突
        self.assertEqual(len(ALIAS_MAP), len(set(ALIAS_MAP.values())))
        for alias in ALIAS_MAP.values():
            self.assertRegex(alias, r"^[a-zA-Z0-9_-]+$")
        # 映射表里的真实名必须是含中文（否则无需映射）
        for real in ALIAS_MAP:
            self.assertNotRegex(real, r"^[a-zA-Z0-9_-]+$")

    def test_mock_schemas_ascii_unique(self):
        reg = ToolRegistry()
        for t in build_mock_tools():
            reg.register(t)
        names = [s["function"]["name"] for s in reg.schemas()]
        for n in names:
            self.assertRegex(n, r"^[a-zA-Z0-9_-]+$")
        self.assertEqual(len(names), len(set(names)))


class TestAgentHelpers(unittest.TestCase):
    def test_extract_json_plain(self):
        self.assertEqual(DeepInvestigationAgent._extract_json('{"a": 1}'), {"a": 1})

    def test_extract_json_fenced(self):
        self.assertEqual(DeepInvestigationAgent._extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_extract_json_with_noise(self):
        self.assertEqual(DeepInvestigationAgent._extract_json('报告如下：{"a": 1}结束'), {"a": 1})

    def test_safe_json_loads(self):
        self.assertEqual(DeepInvestigationAgent._safe_json_loads('{"x":1}'), {"x": 1})
        self.assertEqual(DeepInvestigationAgent._safe_json_loads('bad'), {})

    def test_fallback_report(self):
        ev = SecurityEventInput(event_id="E1", severity="HIGH", target_ip="1.1.1.1", confidence=0.7)
        r = DeepInvestigationAgent._fallback_report(ev, [], reason="测试")
        self.assertTrue(r.need_manual_takeover)
        self.assertIn("证据不足", r.conclusion)

    def test_fallback_report_extracts_knowledge_refs(self):
        """降级报告应提炼已采集证据：knowledge_query 的 evidence_refs + 成功工具返回。"""
        ev = SecurityEventInput(
            event_id="E1", severity="HIGH", target_ip="1.1.1.1",
            confidence=0.7, evidence=["原始证据"],
        )
        records = [
            {"tool": "query_alerts", "input": {"ip": "1.1.1.1"}, "output": "告警列表：[WebShell通信行为告警]", "status": "success"},
            {"tool": "knowledge_query", "input": {"keyword": "WebShell攻击原理"},
             "output": "[知识包·攻击原理]...", "status": "success",
             "evidence_refs": ["MITRE ATT&CK T1505.003 - Server Software Component: Web Shell"]},
            {"tool": "query_asset", "input": {"ip": "2.2.2.2"}, "output": "[失败] 数据不可得", "status": "failed"},
        ]
        r = DeepInvestigationAgent._fallback_report(ev, records, reason="达到最大工具调用次数，证据仍不足")
        # 知识引用进入证据来源
        self.assertIn("知识包引用: MITRE ATT&CK T1505.003 - Server Software Component: Web Shell", r.evidence_source)
        # 成功工具名进入证据来源，失败工具不进入
        self.assertIn("来源工具: query_alerts", r.evidence_source)
        self.assertNotIn("来源工具: query_asset", r.evidence_source)
        # 成功工具返回摘要进入关键证据
        self.assertTrue(any("WebShell通信行为告警" in ev for ev in r.key_evidence))
        self.assertIn("原始证据", r.key_evidence)
        self.assertTrue(r.need_manual_takeover)
        self.assertEqual(r.tool_call_records, records)


class TestAgentConfig(unittest.TestCase):
    """AgentConfig 步数上限：默认值 + 环境变量覆盖（防死循环上限可调）。"""

    def test_default_max_tool_calls(self):
        self.assertEqual(AgentConfig().max_tool_calls, 12)

    def test_default_max_steps(self):
        self.assertEqual(AgentConfig().max_steps, 5)

    def test_env_override_max_tool_calls(self):
        os.environ["AGENT_MAX_TOOL_CALLS"] = "20"
        try:
            self.assertEqual(AgentConfig().max_tool_calls, 20)
        finally:
            del os.environ["AGENT_MAX_TOOL_CALLS"]

    def test_env_invalid_falls_back_to_default(self):
        os.environ["AGENT_MAX_TOOL_CALLS"] = "not-a-number"
        try:
            self.assertEqual(AgentConfig().max_tool_calls, 12)
        finally:
            del os.environ["AGENT_MAX_TOOL_CALLS"]


@unittest.skipUnless(os.getenv("LLM_API_KEY"), "未配置 LLM_API_KEY，跳过集成测试")
class TestFullInvestigation(unittest.TestCase):
    def test_web_shell_full_run(self):
        config = load_config()
        config.tools.mode = "mock"  # 集成测试强制 Mock，避免依赖真实平台
        llm = LLMClient(config.llm)
        reg = ToolRegistry()
        for t in build_mock_tools():
            reg.register(t)
        agent = DeepInvestigationAgent(config, llm, reg)
        with open(SAMPLE, encoding="utf-8") as f:
            ev = SecurityEventInput.from_dict(json.load(f))
        report = agent.investigate(ev)
        d = report.to_dict()
        self.assertTrue(d["conclusion"])
        self.assertIsInstance(d["tool_call_records"], list)
        for k in ["conclusion", "risk_level", "attack_type"]:
            self.assertTrue(d[k], f"{k} 不应为空")


if __name__ == "__main__":
    unittest.main(verbosity=2)
