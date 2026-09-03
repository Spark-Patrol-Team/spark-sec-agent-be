import json
import unittest
from types import SimpleNamespace

from sec_agent.deep_agent.agent import DeepInvestigationAgent
from sec_agent.deep_agent.models import SecurityEventInput


class _DummyLLM:
    available = True


class _DummyTools:
    def schemas(self):
        return []


class DeepAgentEvidenceGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        config = SimpleNamespace(
            agent=SimpleNamespace(max_tool_calls=5)
        )
        self.agent = DeepInvestigationAgent(
            config=config,
            llm=_DummyLLM(),
            tools=_DummyTools(),
        )

        self.event = SecurityEventInput(
            event_id="synthetic-event-001",
            event_type="SyntheticSecurityEvent",
            severity="HIGH",
            timestamp="2026-09-03T12:00:00+08:00",
            source_ip="192.0.2.10",
            target_ip="198.51.100.20",
            alerts=["synthetic-alert-001"],
            evidence=["synthetic-upstream-evidence"],
            initial_verdict="疑似攻击",
            confidence=0.75,
            trace_id="synthetic-trace-001",
            run_id="synthetic-run-001",
        )

    def _llm_report(self, **overrides) -> str:
        data = {
            "event_basic_info": {
                "event_id": self.event.event_id,
                "event_type": self.event.event_type,
                "severity": self.event.severity,
                "timestamp": self.event.timestamp,
                "source_ip": self.event.source_ip,
                "target_ip": self.event.target_ip,
            },
            "conclusion": "基于工具证据形成测试结论",
            "risk_level": "HIGH",
            "attack_type": "SyntheticSecurityEvent",
            "key_evidence": ["synthetic-tool-evidence"],
            "evidence_source": ["synthetic_query"],
            "investigation_steps": [
                {
                    "step_id": 1,
                    "goal": "查询测试证据",
                    "evidence_gap": "需要补充工具结果",
                    "tool": "synthetic_query",
                    "tool_input": {},
                    "tool_output": "synthetic result",
                    "new_evidence": "synthetic-tool-evidence",
                    "conclusion_change": "置信度提高",
                }
            ],
            "attack_chain": "synthetic attack chain",
            "confidence": 0.9,
            "disposal_suggestions": ["人工复核"],
            "need_manual_takeover": False,
            "manual_takeover_reason": "",
            "unresolved_issues": [],
            "affected_objects": ["198.51.100.20"],
        }
        data.update(overrides)
        return json.dumps(data, ensure_ascii=False)

    def test_successful_tool_record_allows_llm_report(self) -> None:
        """真实工具成功且存在有效证据：应接受 LLM 报告。"""
        tool_records = [
            {
                "tool": "synthetic_query",
                "input": {"asset": "198.51.100.20"},
                "output": "synthetic verified evidence",
                "status": "success",
            }
        ]

        report = self.agent._parse_report(
            self._llm_report(),
            self.event,
            tool_records,
        )

        self.assertFalse(report.need_manual_takeover)
        self.assertEqual(report.conclusion, "基于工具证据形成测试结论")
        self.assertEqual(report.tool_call_records, tool_records)
        self.assertEqual(report.confidence, 0.9)

    def test_partial_empty_result_is_not_blocked_by_guard(self) -> None:
        """合法空集 partial：工具执行成功但无命中，不应被无记录门禁误杀。"""
        tool_records = [
            {
                "tool": "synthetic_query",
                "input": {"asset": "198.51.100.20"},
                "output": "合法空集：0 results",
                "status": "partial",
            }
        ]

        report = self.agent._parse_report(
            self._llm_report(
                conclusion="查询成功但当前未发现匹配结果",
                confidence=0.55,
                unresolved_issues=["当前查询结果为空"],
            ),
            self.event,
            tool_records,
        )

        self.assertEqual(report.conclusion, "查询成功但当前未发现匹配结果")
        self.assertEqual(report.tool_call_records, tool_records)
        self.assertFalse(report.need_manual_takeover)

    def test_failed_or_401_tool_record_forces_fallback(self) -> None:
        """401/失败：不得接受 LLM 声称的确定性结论。"""
        tool_records = [
            {
                "tool": "synthetic_query",
                "input": {"asset": "198.51.100.20"},
                "output": "HTTP 401 unauthorized",
                "status": "failed",
            }
        ]

        report = self.agent._parse_report(
            self._llm_report(
                conclusion="攻击已确认",
                confidence=0.99,
            ),
            self.event,
            tool_records,
        )

        self.assertTrue(report.need_manual_takeover)
        self.assertIn("证据不足", report.conclusion)
        self.assertNotEqual(report.conclusion, "攻击已确认")
        self.assertEqual(report.investigation_steps, [])
        self.assertEqual(report.tool_call_records, tool_records)

    def test_no_tool_records_rejects_fabricated_llm_steps(self) -> None:
        """无真实工具记录但 LLM 虚构工具步骤：必须 fallback。"""
        fake_report = self._llm_report(
            conclusion="已通过不存在的工具确认攻击",
            investigation_steps=[
                {
                    "step_id": 1,
                    "goal": "虚构查询",
                    "evidence_gap": "无",
                    "tool": "fabricated_tool",
                    "tool_input": {},
                    "tool_output": "虚构成功结果",
                    "new_evidence": "虚构证据",
                    "conclusion_change": "确认攻击",
                }
            ],
            key_evidence=["fabricated evidence"],
            confidence=0.99,
        )

        report = self.agent._parse_report(
            fake_report,
            self.event,
            [],
        )

        self.assertTrue(report.need_manual_takeover)
        self.assertIn("证据不足", report.conclusion)
        self.assertEqual(report.investigation_steps, [])
        self.assertEqual(report.tool_call_records, [])
        self.assertNotIn("fabricated evidence", report.key_evidence)


if __name__ == "__main__":
    unittest.main()