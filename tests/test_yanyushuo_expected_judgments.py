# -*- coding: utf-8 -*-
"""闫昱硕判据一致性守护测试（确定性，不使用 LLM）。

负责人：闫昱硕；日期：2026-09-06。

校验 `docs/modules/scenario-knowledge/judgments/caseN.expected.json`：
1. 可解析、必填字段齐全、类型正确；
2. 枚举与冻结评测汇总 Schema（knowledge_evaluation_summary.schema.json）一致；
3. `expected_scope` 与 `signal_strength` 合法；
4. 内部一致性（forbidden∩required=∅；required⊆allowed；out_of_scope 禁命中知识；weak 禁套用处置模板）；
5. `case_file` 指向的 fixture 存在且 `case_id` 一致；
6. 与陈敏 `test_yanyushuo_signal_strength_and_verdict` 的期望强度对齐。
"""
from __future__ import annotations

import json
from pathlib import Path

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.services.gatekeeper import SignalStrength, WebShellGatekeeper


REPO = Path(__file__).resolve().parents[1]
JUDGMENTS_DIR = REPO / "docs" / "modules" / "scenario-knowledge" / "judgments"
SCHEMA_FILE = REPO / "tests" / "fixtures" / "evaluation" / "knowledge_evaluation_summary.schema.json"
CASES_DIR = REPO / "docs" / "modules" / "scenario-knowledge" / "knowledge-test-cases"

KNOWN_SCOPES = {"in_scope", "weak_signal", "out_of_scope"}


def _load_schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _load_expected(i: int) -> dict:
    return json.loads((JUDGMENTS_DIR / f"case{i}.expected.json").read_text(encoding="utf-8"))


def _load_input_event(i: int) -> tuple[dict, dict]:
    """读取 case 输入，返回 (原始文件对象, 事件输入对象)。

    正式案例目录存在两种结构：case1-6 为扁平结构（文件本身就是 SecurityEventInput），
    case7-10 为包裹结构（{"case_id", "category", "description", "input_event"}）。
    """
    d = _load_expected(i)
    fixture = json.loads((REPO / d["case_file"]).read_text(encoding="utf-8"))
    return fixture, (fixture.get("input_event") if "input_event" in fixture else fixture)


def _enums() -> dict:
    schema = _load_schema()
    props = schema["$defs"]["evaluation_result"]["properties"]
    return {
        "knowledge_mode": props["knowledge_mode"]["enum"],
        "applicability": props["applicability"]["enum"],
        "knowledge_ids": props["matched_knowledge_ids"]["items"]["enum"],
        "tool_status": schema["$defs"]["tool_call_state"]["enum"],
    }


ENUMS = _enums()
SIGNAL_STRENGTH_VALUES = {s.value for s in SignalStrength}

# Chen Min 交接断言中的期望强度（严格 case 必须完全相等；宽松 case 只须落在允许偏离集合）
CHENMIN_PRIMARY = {
    1: SignalStrength.IN_SCOPE_WEAK,
    2: SignalStrength.IN_SCOPE_WEAK,
    3: SignalStrength.IN_SCOPE_WEAK,
    4: SignalStrength.IN_SCOPE_WEAK,
    5: SignalStrength.IN_SCOPE_WEAK,
    6: SignalStrength.OUT_OF_SCOPE,
    7: SignalStrength.MIXED,
    8: SignalStrength.IN_SCOPE_WEAK,
    9: SignalStrength.IN_SCOPE_CONFIRMED,
    10: SignalStrength.OUT_OF_SCOPE,
}
# 宽松 case（其 test 允许偏离集合）
LOOSE_CASES = {1, 3, 4, 5, 7}


def test_ten_expected_files_present() -> None:
    for i in range(1, 11):
        assert (JUDGMENTS_DIR / f"case{i}.expected.json").exists(), f"缺少 case{i}.expected.json"


def test_expected_files_parse_and_have_required_fields() -> None:
    required = [
        "schema_version",
        "case_id",
        "case_file",
        "signal_strength",
        "expected_scope",
        "knowledge_mode",
        "applicability",
        "allowed_knowledge_ids",
        "required_knowledge_ids",
        "forbidden_knowledge_ids",
        "allowed_conclusions",
        "forbidden_conclusions",
        "required_evidence_gaps",
        "human_required",
        "automatic_checks",
    ]
    for i in range(1, 11):
        d = _load_expected(i)
        for f in required:
            assert f in d, f"case{i}.expected.json 缺少字段 {f}"
        for f in {"allowed_knowledge_ids", "required_knowledge_ids", "forbidden_knowledge_ids"}:
            assert isinstance(d[f], list), f"case{i} {f} 应为 list"
        assert isinstance(d["human_required"], bool), f"case{i} human_required 应为 bool"
        assert isinstance(d["automatic_checks"], list), f"case{i} automatic_checks 应为 list"
        assert isinstance(d["allowed_conclusions"], list), f"case{i} allowed_conclusions 应为 list"
        assert isinstance(d["forbidden_conclusions"], list), f"case{i} forbidden_conclusions 应为 list"
        assert isinstance(d["required_evidence_gaps"], list), f"case{i} required_evidence_gaps 应为 list"


def test_enum_alignment_with_frozen_summary_schema() -> None:
    for i in range(1, 11):
        d = _load_expected(i)
        assert d["knowledge_mode"] in ENUMS["knowledge_mode"], f"case{i} knowledge_mode 不在汇总 Schema 枚举"
        assert d["applicability"] in ENUMS["applicability"], f"case{i} applicability 不在汇总 Schema 枚举"
        for k in d["allowed_knowledge_ids"] + d["required_knowledge_ids"] + d["forbidden_knowledge_ids"]:
            assert k in ENUMS["knowledge_ids"], f"case{i} 知识ID {k} 不在汇总 Schema 枚举"
        ts = d.get("expected_tool_status", {})
        for key, val in (("knowledge_query", ts.get("knowledge_query")), ("mcp_tools", ts.get("mcp_tools"))):
            assert val in ENUMS["tool_status"], f"case{i} tool_status.{key}={val!r} 不在汇总 Schema 枚举"


def test_scope_and_signal_strength_valid() -> None:
    for i in range(1, 11):
        d = _load_expected(i)
        assert d["expected_scope"] in KNOWN_SCOPES, f"case{i} expected_scope 非法"
        ss = d["signal_strength"]
        assert ss["expected_gate_overall"] in SIGNAL_STRENGTH_VALUES, f"case{i} gate overall 非法"
        for dev in ss["allowed_gate_deviations"]:
            assert dev in SIGNAL_STRENGTH_VALUES, f"case{i} 允许偏离 {dev} 非法"


def test_internal_consistency() -> None:
    for i in range(1, 11):
        d = _load_expected(i)
        allowed = set(d["allowed_knowledge_ids"])
        required = set(d["required_knowledge_ids"])
        forbidden = set(d["forbidden_knowledge_ids"])
        assert forbidden.isdisjoint(required), f"case{i} forbidden 与 required 有交集"
        assert required.issubset(allowed), f"case{i} required 必须 ⊆ allowed"
        assert allowed | required | forbidden <= set(ENUMS["knowledge_ids"]), f"case{i} 含未知知识ID"

        scope = d["expected_scope"]
        if scope == "out_of_scope":
            assert d["knowledge_mode"] in {"knowledge_forbidden", "knowledge_not_applicable"}, f"case{i} OOS mode 错误"
            assert allowed == set() and required == set(), f"case{i} OOS 不应允许/要求知识"
            assert forbidden == set(ENUMS["knowledge_ids"]), f"case{i} OOS 应禁止一切 WebShell 知识"
        elif scope == "weak_signal":
            assert d["knowledge_mode"] in {"knowledge_required", "knowledge_optional"}, f"case{i} weak mode 错误"
            # weak 不得无条件套用高风险处置模板
            assert "K-WEBSHELL-RESPONSE-TEMPLATE" in forbidden, f"case{i} weak 必须禁止 RESPONSE-TEMPLATE"
        elif scope == "in_scope":
            assert d["knowledge_mode"] == "knowledge_required", f"case{i} in_scope mode 应为 knowledge_required"
            assert d["applicability"] == "applicable", f"case{i} in_scope applicability 应为 applicable"


def test_case_file_references_existing_fixture() -> None:
    for i in range(1, 11):
        d = _load_expected(i)
        case_file = REPO / d["case_file"]
        assert case_file.exists(), f"case{i} case_file 不存在: {d['case_file']}"
        fixture = json.loads(case_file.read_text(encoding="utf-8"))
        if "case_id" in fixture:
            assert fixture["case_id"] == d["case_id"], (
                f"case{i} 判据 case_id={d['case_id']} 与 fixture {fixture['case_id']} 不一致"
            )
        else:
            assert "event_id" in fixture, f"case{i} 扁平结构 fixture 应含 event_id"


def test_alignment_with_chenmin_signal_strength() -> None:
    for i in range(1, 11):
        d = _load_expected(i)
        primary = CHENMIN_PRIMARY[i]
        expected_overall = SignalStrength(d["signal_strength"]["expected_gate_overall"])
        allowed = {SignalStrength(x) for x in d["signal_strength"]["allowed_gate_deviations"]}
        if i in LOOSE_CASES:
            assert expected_overall in allowed, f"case{i} 期望强度需落在允许偏离集合"
            assert primary in allowed, f"case{i} 允许偏离集合应包含陈敏主期望 {primary}"
        else:
            assert expected_overall == primary, f"case{i} 期望强度应为 {primary}，实际 {expected_overall}"


def test_actual_gate_output_matches_expected() -> None:
    """用陈敏最新门禁跑 10 案，断言实际 overall_strength 落在判据允许集合内。"""
    gk = WebShellGatekeeper()
    for i in range(1, 11):
        d = _load_expected(i)
        _, input_event = _load_input_event(i)
        evt = SecurityEventInput.from_dict(input_event)
        result = gk.audit(evt)
        allowed = {SignalStrength(x) for x in d["signal_strength"]["allowed_gate_deviations"]}
        assert result.overall_strength in allowed, (
            f"case{i} 门禁实际 {result.overall_strength} 不在判据允许集合 {allowed}"
        )
        # 非宽松 case 要求严格相等
        if i not in LOOSE_CASES:
            assert result.overall_strength == SignalStrength(
                d["signal_strength"]["expected_gate_overall"]
            ), f"case{i} 门禁实际 {result.overall_strength} 应等于判据期望"
