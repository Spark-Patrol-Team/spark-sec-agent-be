# -*- coding: utf-8 -*-
"""深度调查 Agent 测试。

运行（在项目根目录）：
  python -m unittest test.test_agent -v
  或
  python test/test_agent.py

说明：单元测试不依赖 LLM；集成测试需要配置 LLM_API_KEY 后才会执行。
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep_agent.models import SecurityEventInput, InvestigationReport
from deep_agent.tools.mock import build_mock_tools
from deep_agent.tools.base import ToolRegistry
from deep_agent.agent import DeepInvestigationAgent
from deep_agent.config import load_config
from deep_agent.llm import LLMClient

SAMPLE = Path(__file__).resolve().parent / "sample_event.json"


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
