import os
import sys
import types
import unittest
from unittest import mock

from sec_agent.domain.models import (
    BusinessStatus,
    InvestigationReport,
    Priority,
    SecurityEvent,
    StartRunRequest,
    TriageResult,
    TruthVerdict,
)
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.deep_agent_bridge import DeepAgentBridge, DeepAgentBridgeUnavailable
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.gatekeeper import GateDecision, WebShellGatekeeper
from sec_agent.services.investigation import DeepInvestigationAgent
from sec_agent.services.orchestrator import Orchestrator
from sec_agent.services.triage import RiskTriageService


class DeepAgentBridgeTest(unittest.TestCase):
    def test_fixed_sample_real_path_allows_guarded_knowledge(self) -> None:
        adapter = FixedSampleAdapter()
        alerts = adapter.fetch_alerts(sample_id="webshell-001")
        event = AlertCorrelationService().correlate(alerts)
        triage = RiskTriageService().triage(event, alerts)
        bridge = DeepAgentBridge()
        modules = bridge._load_modules()
        deep_event = modules["SecurityEventInput"].from_dict(
            bridge._to_deep_agent_input(
                trace_id="trace-real-path",
                run_id="run-real-path",
                event=event,
                triage=triage,
            )
        )

        gate = WebShellGatekeeper().audit(deep_event)

        self.assertEqual(deep_event.event_type, "webshell")
        self.assertEqual(gate.gate_decision, GateDecision.IN_SCOPE)
        self.assertTrue(any("Web 进程派生 shell 进程" in item for item in deep_event.evidence))

        config = modules["load_config"]()
        config.tools.mode = "mock"
        config.tools.knowledge_mode = "guarded"
        registry = bridge._build_tools(modules, config, gate_decision=gate.gate_decision.value)
        result = registry.get("knowledge_query").call({"keyword": "WebShell攻击原理"})
        self.assertEqual(result.status, "success")
        self.assertTrue(result.data["knowledge_returned"])

    def test_malicious_non_webshell_real_path_does_not_release_knowledge(self) -> None:
        adapter = FixedSampleAdapter()
        source = adapter.fetch_alerts(sample_id="webshell-001")[0]
        alert = source.model_copy(
            update={
                "alert_type": "lateral_movement",
                "name": "SMB 横向移动告警",
                "raw_severity": "critical",
                "evidence_refs": [],
            }
        )
        event = AlertCorrelationService().correlate([alert])
        triage = RiskTriageService().triage(event, [alert])
        bridge = DeepAgentBridge()
        modules = bridge._load_modules()
        deep_event = modules["SecurityEventInput"].from_dict(
            bridge._to_deep_agent_input(
                trace_id="trace-non-webshell",
                run_id="run-non-webshell",
                event=event,
                triage=triage,
            )
        )

        gate = WebShellGatekeeper().audit(deep_event)

        self.assertEqual(triage.verdict, TruthVerdict.MALICIOUS)
        self.assertEqual(gate.gate_decision, GateDecision.OUT_OF_SCOPE)

    def test_evidence_summary_is_joined_by_ref_not_list_position(self) -> None:
        event = self._event().model_copy(
            update={
                "evidence_summaries": {
                    "evidence-with-summary": "Web 进程派生 shell 进程",
                }
            }
        )
        triage = self._triage().model_copy(
            update={
                "supporting_evidence_refs": [
                    "evidence-without-summary",
                    "evidence-with-summary",
                ]
            }
        )

        payload = DeepAgentBridge()._to_deep_agent_input(
            trace_id="trace-ref-map",
            run_id="run-ref-map",
            event=event,
            triage=triage,
        )

        self.assertEqual(payload["evidence"][0], "evidence-without-summary")
        self.assertEqual(
            payload["evidence"][1],
            "evidence-with-summary: Web 进程派生 shell 进程",
        )

    def test_guarded_mode_without_gate_result_does_not_register_knowledge(self) -> None:
        bridge = DeepAgentBridge()
        modules = bridge._load_modules()
        config = modules["load_config"]()
        config.tools.mode = "mock"
        config.tools.knowledge_mode = "guarded"

        registry = bridge._build_tools(modules, config, gate_decision=None)

        self.assertNotIn("knowledge_query", registry.names())

    def test_guarded_mode_registers_gate_bound_knowledge(self) -> None:
        bridge = DeepAgentBridge()
        modules = bridge._load_modules()
        config = modules["load_config"]()
        config.tools.mode = "mock"
        config.tools.knowledge_mode = "guarded"

        registry = bridge._build_tools(modules, config, gate_decision="weak_signal")
        result = registry.get("knowledge_query").call({"keyword": "WebShell 植入方式"})

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.data["knowledge_returned"])

    def test_guarded_mode_out_of_scope_does_not_expose_webshell_knowledge(self) -> None:
        bridge = DeepAgentBridge()
        modules = bridge._load_modules()
        config = modules["load_config"]()
        config.tools.mode = "mock"
        config.tools.knowledge_mode = "guarded"

        registry = bridge._build_tools(modules, config, gate_decision="out_of_scope")

        self.assertNotIn("knowledge_query", registry.names())

    def test_deep_agent_backend_maps_external_report_to_domain_report(self) -> None:
        old_modules = dict(sys.modules)
        self._install_fake_deep_agent()
        try:
            # 固定 mock 工具模式，避免开发机环境变量把 fake deep_agent 切到真实 MCP 模式。
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
        service = DeepInvestigationAgent(platform=_NoopPlatform(), backend="deep_agent", bridge=_UnavailableBridge())

        report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")

        self.assertTrue(report.needs_human)
        self.assertEqual(report.conclusion, TruthVerdict.UNCERTAIN)
        self.assertIn("deep_agent", report.summary)

    def test_auto_backend_records_fallback_and_runs_internal_tool_chain(self) -> None:
        service = DeepInvestigationAgent(platform=FixedSampleAdapter(), backend="auto", bridge=_UnavailableBridge())

        report = service.investigate("trace-test", self._event(), self._triage(), run_id="run-test")

        self.assertFalse(report.needs_human)
        self.assertIn("已回退内部工具调查子链", report.summary)
        self.assertTrue(any("deep_agent 不可用" in item for item in report.unresolved_questions))
        self.assertEqual(
            [step.tool_request.tool_name for step in report.steps if step.tool_request],
            ["evidence_lookup", "xdr_log_query"],
        )
        self.assertEqual(len(report.tool_results), 2)

    def test_orchestrator_uses_injected_bridge_for_main_chain_investigation(self) -> None:
        bridge = _SuccessfulBridge()
        orchestrator = Orchestrator(
            platform=FixedSampleAdapter(),
            store=InMemoryEventRepository(),
            investigation_backend="deep_agent",
            investigation_bridge=bridge,
        )

        ctx = orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        self.assertEqual(bridge.calls, 1)
        self.assertIsNotNone(ctx.investigation)
        self.assertEqual(ctx.investigation.summary, "注入 Bridge 已完成调查")
        self.assertEqual(ctx.investigation.tool_results, ["bridge-tool-call"])

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
            event_type="webshell",
            alert_summaries={"FIX-XDR-WEBSHELL-001": "WebShell 上传后命令执行"},
            evidence_summaries={
                "FIX-XDR-WEBSHELL-001:alert_name": "Web 进程派生 shell 进程"
            },
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


class _SuccessfulBridge:
    def __init__(self) -> None:
        self.calls = 0

    def investigate(self, trace_id, run_id, event, triage):
        self.calls += 1
        return InvestigationReport(
            conclusion=triage.verdict,
            final_confidence=0.93,
            timeline=["注入 Bridge 调查完成"],
            tool_results=["bridge-tool-call"],
            key_evidence_refs=list(triage.supporting_evidence_refs),
            evidence_relations=["注入 Bridge 输出的证据关系"],
            affected_objects=event.entities.get("assets", []) or event.entities.get("dst_ips", []),
            unresolved_questions=[],
            recommended_actions=["隔离目标主机"],
            needs_human=False,
            steps=[],
            summary="注入 Bridge 已完成调查",
        )


if __name__ == "__main__":
    unittest.main()
