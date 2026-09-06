import json
from pathlib import Path

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.deep_agent.tools.knowledge import (
    KnowledgeEntry,
    KnowledgeQueryTool,
)
from sec_agent.services.gatekeeper import WebShellGatekeeper


CASES_DIR = Path(__file__).resolve().parent / "fixtures" / "gatekeeper_cases"


def _load_case(i: int) -> dict:
    return json.loads(
        (CASES_DIR / f"case{i}.json").read_text(encoding="utf-8")
    )


def _build_tool(overall_strength: str) -> KnowledgeQueryTool:
    entries = [
        KnowledgeEntry(
            name="攻击原理",
            keywords=["WebShell攻击原理"],
            content="TEST_WEBSHELL_CONFIRMATORY_CONTENT",
            evidence_refs=["test-ref"],
        )
    ]

    return KnowledgeQueryTool(
        entries=entries,
        event_context={"overall_strength": overall_strength},
    )


def test_case1_10_knowledge_gate_matches_gatekeeper():
    expected_gate = {
        1: "weak_signal",
        2: "in_scope",
        3: "weak_signal",
        4: "weak_signal",
        5: "weak_signal",
        6: "out_of_scope",
        7: "weak_signal",
        8: "weak_signal",
        9: "in_scope",
        10: "out_of_scope",
    }

    gatekeeper = WebShellGatekeeper()

    for idx, expected in expected_gate.items():
        case = _load_case(idx)
        event = SecurityEventInput.from_dict(case["input_event"])
        gate_result = gatekeeper.audit(event)

        tool = _build_tool(gate_result.overall_strength.value)
        result = tool.call({"keyword": "WebShell攻击原理"})

        if expected == "out_of_scope":
            assert result.status == "failed"
            assert result.error == "knowledge_scope_mismatch"
            assert "TEST_WEBSHELL_CONFIRMATORY_CONTENT" not in result.summary

        elif expected == "weak_signal":
            assert result.status == "partial"
            assert result.data["gate"] == "weak_signal"
            assert result.data["knowledge_returned"] is False
            assert "TEST_WEBSHELL_CONFIRMATORY_CONTENT" not in result.summary

        else:
            assert result.status == "success"
            assert "TEST_WEBSHELL_CONFIRMATORY_CONTENT" in result.summary


def test_case6_and_case10_never_return_webshell_content():
    gatekeeper = WebShellGatekeeper()

    for idx in (6, 10):
        case = _load_case(idx)
        event = SecurityEventInput.from_dict(case["input_event"])
        gate_result = gatekeeper.audit(event)

        tool = _build_tool(gate_result.overall_strength.value)
        result = tool.call({"keyword": "WebShell攻击原理"})

        assert result.error == "knowledge_scope_mismatch"
        assert "TEST_WEBSHELL_CONFIRMATORY_CONTENT" not in result.summary