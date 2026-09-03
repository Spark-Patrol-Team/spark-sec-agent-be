import os
import sys
import types
import unittest
from unittest import mock

from sec_agent.domain.models import BusinessStatus, SecurityEvent, TriageResult, TruthVerdict, Priority
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.services.deep_agent_bridge import DeepAgentBridgeUnavailable
from sec_agent.services.investigation import DeepInvestigationAgent


class DeepAgentBridgeTest(unittest.TestCase):
    def test_deep_agent_backend_maps_external_report_to_domain_report(self) -> None:
        old_modules = dict(sys.modules)
        self._install_fake_deep_agent()
        try:
            # 隔离生产环境变量：DEEP_AGENT_TOOL_MODE=mcp/auto 会经桥接 _override_config
            # 覆盖 fake config 的工具模式，导致 fake deep_agent 缺少 MCP 工具时桥接不可用、
            # 返回人工接管；本用例固定走 mock 工具映射，与机器环境变量解耦。
            with mock.patch.dict(os.environ, {"DEEP_AGENT_TOOL_MODE": ""}):
                service = DeepInvestigationAgent(platform=_NoopPlatform(), backend="deep_agent")
                report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")
        finally:
            self._restore_modules(old_modules)

        self.assertFalse(report.needs_human)
        self.assertEqual(report.summary, "确认 WebShell 攻击成立")
        self.assertEqual(report.final_confidence, 0.91)
        self.assertEqual(report.recommended_actions, ["隔离目标主机", "保留取证副本"])
        self.assertEqual(report.affected_objects, ["198.51.100.11"])
        self.assertIn("WebShell 上传后命令执行", report.evidence_relations)
        self.assertEqual(report.steps[0].goal, "查询资产和关联告警")

    def test_deep_agent_backend_returns_human_required_when_unavailable(self) -> None:
        service = DeepInvestigationAgent(platform=_NoopPlatform(), backend="deep_agent")
        service._deep_agent_bridge = _UnavailableBridge()

        report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")

        self.assertTrue(report.needs_human)
        self.assertEqual(report.conclusion, TruthVerdict.UNCERTAIN)
        self.assertIn("deep_agent", report.summary)

    def test_auto_backend_records_fallback_and_runs_internal_tool_chain(self) -> None:
        service = DeepInvestigationAgent(platform=FixedSampleAdapter(), backend="auto")
        service._deep_agent_bridge = _UnavailableBridge()

        report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")

        self.assertFalse(report.needs_human)
        self.assertIn("已回退内部工具调查子链", report.summary)
        self.assertTrue(any("deep_agent 不可用" in item for item in report.unresolved_questions))
        self.assertEqual(
            [step.tool_request.tool_name for step in report.steps if step.tool_request],
            ["evidence_lookup", "xdr_log_query"],
        )
        self.assertEqual(len(report.tool_results), 2)

    def _install_fake_deep_agent(self) -> None:
        package = types.ModuleType("deep_agent")
        config_module = types.ModuleType("deep_agent.config")
        llm_module = types.ModuleType("deep_agent.llm")
        models_module = types.ModuleType("deep_agent.models")
        agent_module = types.ModuleType("deep_agent.agent")
        tools_package = types.ModuleType("deep_agent.tools")
        tools_base_module = types.ModuleType("deep_agent.tools.base")
        tools_mock_module = types.ModuleType("deep_agent.tools.mock")

        class Config:
            def __init__(self) -> None:
                self.llm = object()
                self.tools = types.SimpleNamespace(mode="mock")

        class LLMClient:
            available = True

            def __init__(self, config) -> None:
                self.config = config

        class SecurityEventInput:
            @classmethod
            def from_dict(cls, data):
                instance = cls()
                instance.data = data
                return instance

        class ToolRegistry:
            def __init__(self) -> None:
                self.tools = []

            def register(self, tool):
                self.tools.append(tool)

        class DeepAgentReport:
            def to_dict(self):
                return {
                    "conclusion": "确认 WebShell 攻击成立",
                    "confidence": 0.91,
                    "key_evidence": ["FIX-XDR-WEBSHELL-001:alert_name"],
                    "investigation_steps": [
                        {
                            "step_id": 1,
                            "goal": "查询资产和关联告警",
                            "tool": "query_asset",
                            "tool_output": "目标为 Web 服务器",
                            "new_evidence": "目标资产存在 WebShell 告警",
                        }
                    ],
                    "tool_call_records": [{"tool": "query_asset", "status": "success"}],
                    "attack_chain": "WebShell 上传后命令执行",
                    "disposal_suggestions": ["隔离目标主机", "保留取证副本"],
                    "need_manual_takeover": False,
                    "unresolved_issues": [],
                    "affected_objects": ["198.51.100.11"],
                }

        class DeepAgent:
            def __init__(self, config, llm, tools) -> None:
                self.config = config
                self.llm = llm
                self.tools = tools

            def investigate(self, event):
                return DeepAgentReport()

        config_module.load_config = Config
        llm_module.LLMClient = LLMClient
        models_module.SecurityEventInput = SecurityEventInput
        tools_base_module.ToolRegistry = ToolRegistry
        tools_mock_module.build_mock_tools = lambda: [object()]
        agent_module.DeepInvestigationAgent = DeepAgent
        sys.modules.update(
            {
                "deep_agent": package,
                "deep_agent.config": config_module,
                "deep_agent.llm": llm_module,
                "deep_agent.models": models_module,
                "deep_agent.agent": agent_module,
                "deep_agent.tools": tools_package,
                "deep_agent.tools.base": tools_base_module,
                "deep_agent.tools.mock": tools_mock_module,
            }
        )

    def _restore_modules(self, old_modules: dict) -> None:
        for name in list(sys.modules):
            if name.startswith("deep_agent"):
                del sys.modules[name]
        sys.modules.update({name: module for name, module in old_modules.items() if name.startswith("deep_agent")})

    def _event(self) -> SecurityEvent:
        return SecurityEvent(
            event_id="evt-test",
            alert_refs=["FIX-XDR-WEBSHELL-001"],
            first_seen_at=__import__("datetime").datetime.fromisoformat("2026-08-20T14:21:15+08:00"),
            last_seen_at=__import__("datetime").datetime.fromisoformat("2026-08-20T14:21:15+08:00"),
            entities={"src_ips": ["198.51.100.33"], "dst_ips": ["198.51.100.11"], "assets": ["198.51.100.11"]},
            correlation_reason="测试关联",
            alert_count_before=1,
            event_count_after=1,
            summary="WebShell 高危事件",
        )

    def _triage(self) -> TriageResult:
        return TriageResult(
            verdict=TruthVerdict.MALICIOUS,
            confidence=0.85,
            risk_score=95,
            priority=Priority.HIGH,
            supporting_evidence_refs=["FIX-XDR-WEBSHELL-001:alert_name"],
            should_investigate=True,
            summary="高风险，需要深度调查",
        )


class _NoopPlatform:
    pass


class _UnavailableBridge:
    def investigate(self, trace_id, run_id, event, triage):
        raise DeepAgentBridgeUnavailable("单元测试模拟 deep_agent 缺失")


if __name__ == "__main__":
    unittest.main()
