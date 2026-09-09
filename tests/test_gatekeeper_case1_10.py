# -*- coding: utf-8 -*-
"""WebShell 门禁自动化测试（确定性逻辑，不使用 LLM）。

负责人/执行人：陈敏
日期：2026-09-08

覆盖：
- Task1：SecurityEventInput 仅允许白名单字段读取。
- Task2：信号 6 级分类 + 来源标注（event_type / alerts / evidence / triage / initial_verdict）。
- Task3：case1-10 输入质量检查（唯一性 / 必填 / 类型 / 矛盾 / 负向约束）。
- Task4：case1-10 门禁可读取信号标注（禁止反向补入知识库证据）。
- Task5：门禁三档判定 in_scope / weak_signal / out_of_scope（不再做 95/75 风险评分升级）。
- Task6：三方交接（杨嘉琪三档门禁、闫昱硕信号强弱、李雨妍合同对齐）。

案例直接读取项目正式案例目录 docs/modules/scenario-knowledge/knowledge-test-cases，
兼容 case1-6 扁平结构与 case7-10 包裹结构，不再维护第二套案例内容。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.services.gatekeeper import (
    GATEKEEPER_WHITELIST_FIELDS,
    GateDecision,
    SignalSource,
    SignalStrength,
    WebShellGatekeeper,
)


FORMAL_CASES_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "modules"
    / "scenario-knowledge"
    / "knowledge-test-cases"
)

# case1-6 为扁平结构（等价于 input_event），其 case_id/category/description 取自《案例描述.md》。
CASE_METADATA = {
    1: ("TC-KNOWLEDGE-001", "正向变体", "IIS WebShell（UpdateChecker.aspx）"),
    2: ("TC-KNOWLEDGE-002", "正向变体", "PassiveNeuron 中的 ASPX WebShell 部署尝试"),
    3: ("TC-KNOWLEDGE-003", "正向变体", "Beima WebShell（WordPress/cPanel）"),
    4: ("TC-KNOWLEDGE-004", "证据不足", "单条告警，缺少上下文"),
    5: ("TC-KNOWLEDGE-005", "证据不足", "XDR 查询失败"),
    6: ("TC-KNOWLEDGE-006", "纯非WebShell负向对照", "WordPress插件/供应链异常，无WebShell证据"),
}


def _load_case(i: int) -> dict:
    raw = json.loads((FORMAL_CASES_DIR / f"case{i}.json").read_text(encoding="utf-8"))
    if "input_event" in raw:
        # case7-10 为包裹结构：{case_id, category, description, input_event}
        return raw
    case_id, category, description = CASE_METADATA[i]
    return {"case_id": case_id, "category": category, "description": description, "input_event": raw}


def _case_available(i: int) -> bool:
    """正式案例文件是否随分支提供。case7-10 由 PR44 提供，未合并时跳过。"""
    return (FORMAL_CASES_DIR / f"case{i}.json").exists()


def load_all_cases() -> list[dict]:
    return [_load_case(i) for i in range(1, 11) if _case_available(i)]


def _require_case(i: int) -> None:
    if not _case_available(i):
        pytest.skip(f"case{i} 正式案例文件未随本分支提供（由 PR44 提供），待合并后可测")


def _inp(case: dict) -> dict:
    return case["input_event"]


EXPECTED_WHITELIST = {
    "event_id",
    "event_type",
    "severity",
    "timestamp",
    "source_ip",
    "target_ip",
    "alerts",
    "evidence",
    "triage",
    "initial_verdict",
}


class TestTask1FieldWhitelist:
    def test_whitelist_contains_contract_fields(self) -> None:
        assert set(GATEKEEPER_WHITELIST_FIELDS) == EXPECTED_WHITELIST
        # 真实合同字段 triage 属于信号来源白名单，允许读取
        assert "triage" in GATEKEEPER_WHITELIST_FIELDS

    def test_confidence_trace_and_run_are_forbidden(self) -> None:
        forbidden_extra = {"confidence", "trace_id", "run_id"}
        assert forbidden_extra.isdisjoint(GATEKEEPER_WHITELIST_FIELDS)

    def test_gatekeeper_filter_drops_forbidden_fields(self) -> None:
        gk = WebShellGatekeeper()
        raw = {
            "event_id": "e1",
            "event_type": "WebShell",
            "severity": "HIGH",
            "timestamp": "t",
            "source_ip": "1.1.1.1",
            "target_ip": "2.2.2.2",
            "alerts": ["a"],
            "evidence": ["e"],
            "triage": {"verdict": "uncertain", "confidence": 0.5},
            "initial_verdict": "v",
            "confidence": 0.9,
            "trace_id": "T",
            "run_id": "R",
        }
        filtered = gk.filter_input(raw)
        assert set(filtered.keys()) == EXPECTED_WHITELIST
        assert "confidence" not in filtered
        assert "trace_id" not in filtered
        assert "run_id" not in filtered
        assert "triage" in filtered

    def test_all_cases_input_model_contains_whitelist_fields(self) -> None:
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(_inp(case))
            data = evt.to_dict()
            missing = [f for f in EXPECTED_WHITELIST if f not in data]
            assert not missing, f"{case['case_id']} 缺少门禁白名单字段: {missing}"


class TestTask3CaseInputQuality:
    def test_all_cases_load_via_security_event_input(self) -> None:
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(_inp(case))
            assert evt.event_id, case["case_id"]
            assert evt.event_type is not None, case["case_id"]
            assert isinstance(evt.evidence, list), case["case_id"]

    def test_case_ids_unique(self) -> None:
        ids = [c["case_id"] for c in load_all_cases()]
        assert len(ids) > 0, "正式案例目录为空"
        assert len(set(ids)) == len(ids), f"重复 case_id: {[i for i in ids if ids.count(i) > 1]}"

    def test_event_ids_unique(self) -> None:
        ids = [_inp(c)["event_id"] for c in load_all_cases()]
        assert len(ids) > 0, "正式案例目录为空"
        assert len(set(ids)) == len(ids), f"重复 event_id: {[i for i in ids if ids.count(i) > 1]}"

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_required_fields_present(self, case_data: dict) -> None:
        inp = _inp(case_data)
        for f in [
            "event_id",
            "event_type",
            "severity",
            "timestamp",
            "source_ip",
            "target_ip",
            "initial_verdict",
            "confidence",
            "evidence",
        ]:
            assert f in inp, f"{case_data['case_id']} 缺少必填字段 {f}"

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_field_types_correct(self, case_data: dict) -> None:
        inp = _inp(case_data)
        assert isinstance(inp["event_id"], str)
        assert isinstance(inp["event_type"], str)
        assert isinstance(inp["severity"], str)
        assert isinstance(inp["timestamp"], str)
        assert isinstance(inp["source_ip"], str)
        assert isinstance(inp["target_ip"], str)
        assert isinstance(inp["evidence"], list)
        assert isinstance(inp["confidence"], (int, float))
        assert 0.0 <= float(inp["confidence"]) <= 1.0
        if "alerts" in inp:
            assert isinstance(inp["alerts"], list)
        if "triage" in inp:
            assert isinstance(inp["triage"], dict)

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_no_explicit_expected_answer_in_input(self, case_data: dict) -> None:
        text = json.dumps(_inp(case_data), ensure_ascii=False)
        assert "期望" not in text
        assert "expected" not in text.lower()

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_category_and_description_annotated(self, case_data: dict) -> None:
        assert case_data.get("category"), f"{case_data['case_id']} 缺少 synthetic 性质 category"
        assert case_data.get("description"), f"{case_data['case_id']} 缺少 description"

    def test_case6_is_pure_non_webshell_negative(self) -> None:
        _require_case(6)
        case6 = _load_case(6)
        assert case6["category"] == "纯非WebShell负向对照"
        inp = _inp(case6)
        assert inp["event_type"] == "WordPress_Compromise"
        combined = " ".join([str(x) for x in inp["alerts"]]) + " " + " ".join(
            [str(x) for x in inp["evidence"]]
        )
        for forbidden in ("WebShell文件", "shell.php", "cmd.exe", "w3wp.exe", "Process.Start"):
            assert forbidden not in combined, f"负向 case6 不应包含 {forbidden}"

    def test_case7_legal_base64_must_not_default_malicious(self) -> None:
        _require_case(7)
        inp = _inp(_load_case(7))
        combined = " ".join(str(x) for x in inp["evidence"])
        assert "已知业务API" in combined
        assert "正常调用记录" in combined
        assert "image/png" in combined

    def test_case8_only_suspicious_filename(self) -> None:
        _require_case(8)
        inp = _inp(_load_case(8))
        combined = " ".join(str(x) for x in inp["evidence"])
        assert "shell.php" in combined
        assert "未检测到对应的HTTP请求记录" in combined
        assert "未检测到该文件被访问或执行的记录" in combined

    def test_case9_has_web_process_and_abnormal_post(self) -> None:
        _require_case(9)
        inp = _inp(_load_case(9))
        combined = " ".join(str(x) for x in inp["evidence"])
        assert "异常POST" in combined or "POST请求" in combined
        assert "w3wp.exe" in combined
        assert "cmd.exe" in combined
        assert "Process.Start" in combined or "子进程 cmd.exe" in combined

    def test_case10_is_ssh_brute_out_of_scope(self) -> None:
        _require_case(10)
        inp = _inp(_load_case(10))
        combined = " ".join(str(x) for x in inp["evidence"])
        assert "SSH" in combined
        assert "暴力破解" in combined
        assert "未检测到该源IP对Web端口的任何访问请求" in combined


class TestTask2SignalClassificationAndSources:
    def test_every_signal_has_annotated_source(self) -> None:
        gk = WebShellGatekeeper()
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(_inp(case))
            result = gk.audit(evt)
            for s in result.signals:
                assert s.source in {
                    SignalSource.EVENT_TYPE,
                    SignalSource.ALERTS,
                    SignalSource.EVIDENCE,
                    SignalSource.TRIAGE,
                    SignalSource.INITIAL_VERDICT,
                }, f"{case['case_id']} 信号 {s.name} 来源未标注"

    def test_initial_verdict_not_labeled_as_triage(self) -> None:
        """修复：initial_verdict 内容不得再标记为 triage 来源。"""
        gk = WebShellGatekeeper()
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(_inp(case))
            result = gk.audit(evt)
            for s in result.signals:
                if s.source == SignalSource.TRIAGE:
                    assert "initial_verdict" not in s.name, (
                        f"{case['case_id']} triage 来源信号不应由 initial_verdict 命名: {s.name}"
                    )

    def test_triage_signal_only_from_triage_field(self) -> None:
        """triage 来源信号只能由 triage 字段产生；无 triage 字段的案例不得出现该来源信号。"""
        gk = WebShellGatekeeper()
        for case in load_all_cases():
            inp = _inp(case)
            evt = SecurityEventInput.from_dict(inp)
            result = gk.audit(evt)
            has_triage_field = isinstance(inp.get("triage"), dict)
            triage_sigs = [s for s in result.signals if s.source == SignalSource.TRIAGE]
            if not has_triage_field:
                assert not triage_sigs, f"{case['case_id']} 无 triage 字段却出现 triage 来源信号"

    def test_no_signal_is_fabricated_from_knowledge(self) -> None:
        _require_case(9)
        gk = WebShellGatekeeper()
        case9 = _load_case(9)
        evt = SecurityEventInput.from_dict(_inp(case9))
        result = gk.audit(evt)
        evidence_texts = set(_inp(case9)["evidence"])
        for s in result.signals:
            if s.source == SignalSource.EVIDENCE:
                assert (
                    s.description in evidence_texts
                ), f"证据信号必须来自输入 evidence，不得反向补入知识库: {s.description}"

    def test_six_strength_levels_are_all_reachable_in_10_cases(self) -> None:
        if not all(_case_available(i) for i in (6, 7, 8, 9, 10)):
            pytest.skip("覆盖强度等级所需的 case6-10 未随本分支提供（由 PR44 提供）")
        gk = WebShellGatekeeper()
        found: set[SignalStrength] = set()
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(_inp(case))
            result = gk.audit(evt)
            found.add(result.overall_strength)
            for s in result.signals:
                found.add(s.strength)
        assert SignalStrength.OUT_OF_SCOPE in found, "缺少 OUT_OF_SCOPE 覆盖（case6/10）"
        assert SignalStrength.IN_SCOPE_CONFIRMED in found, "缺少 IN_SCOPE_CONFIRMED 覆盖（case9）"
        assert SignalStrength.IN_SCOPE_WEAK in found, "缺少 IN_SCOPE_WEAK 覆盖（case1-5/8）"
        assert SignalStrength.BENIGN_LIKE in found, "缺少 BENIGN_LIKE 覆盖（case7）"


class TestTask4CaseSignalAnnotations:
    def _run(self, idx: int) -> tuple[dict, SecurityEventInput, WebShellGatekeeper, object]:
        _require_case(idx)
        case = _load_case(idx)
        evt = SecurityEventInput.from_dict(_inp(case))
        gk = WebShellGatekeeper()
        return case, evt, gk, gk.audit(evt)

    def test_case1_iis_aspx_weak_signals(self) -> None:
        case, _, _, result = self._run(1)
        sig_names = {s.name for s in result.signals}
        assert "event_type_webshell" in sig_names
        alert_sources = [s for s in result.signals if s.source == SignalSource.ALERTS]
        assert alert_sources, f"{case['case_id']} 必须从 alerts 提取信号"
        assert result.overall_strength in {
            SignalStrength.IN_SCOPE_WEAK,
            SignalStrength.IN_SCOPE_CONFIRMED,
        }

    def test_case2_passiveneuron_deployment_attempt_weak(self) -> None:
        case, _, _, result = self._run(2)
        # 正式 case2（PassiveNeuron 部署尝试，被阻断）为弱信号，不应判为确认级
        assert result.overall_strength == SignalStrength.IN_SCOPE_WEAK, (
            f"{case['case_id']} 部署尝试未成功应为 IN_SCOPE_WEAK，实际={result.overall_strength}"
        )
        strong = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        assert not strong, f"{case['case_id']} 正式案例不应含确认级信号"

    def test_case3_beima_weak(self) -> None:
        _, _, _, result = self._run(3)
        assert result.overall_strength == SignalStrength.IN_SCOPE_WEAK

    def test_case4_insufficient_evidence(self) -> None:
        _, _, _, result = self._run(4)
        assert result.overall_strength in {
            SignalStrength.IN_SCOPE_WEAK,
            SignalStrength.INDETERMINATE,
        }
        assert result.evidence_gaps, "证据不足案例必须有证据缺口清单"

    def test_case5_xdr_timeout_gaps(self) -> None:
        _, _, _, result = self._run(5)
        assert result.evidence_gaps

    def test_case6_wordpress_supply_chain_out_of_scope(self) -> None:
        case, _, _, result = self._run(6)
        assert result.overall_strength == SignalStrength.OUT_OF_SCOPE, (
            f"{case['case_id']} 必须判定 OUT_OF_SCOPE，实际={result.overall_strength}"
        )
        strong_ws = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        weak_ws = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_WEAK and s.source != SignalSource.EVENT_TYPE]
        assert not strong_ws, f"{case['case_id']} 负向案例不得含 IN_SCOPE_CONFIRMED"
        assert not weak_ws, f"{case['case_id']} 不得通过 evidence/alerts 注入 WebShell 弱信号"

    def test_case7_legal_upload_benign(self) -> None:
        _, _, _, result = self._run(7)
        benign = [s for s in result.signals if s.strength == SignalStrength.BENIGN_LIKE]
        assert benign, "合法 Base64 上传必须命中 BENIGN_LIKE 信号"
        confirmed_ws = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        assert not confirmed_ws, "合法上传不应出现 IN_SCOPE_CONFIRMED"

    def test_case8_only_filename_weak(self) -> None:
        case, _, _, result = self._run(8)
        assert result.overall_strength == SignalStrength.IN_SCOPE_WEAK, (
            f"{case['case_id']} 仅文件名可疑应为 IN_SCOPE_WEAK，实际={result.overall_strength}"
        )
        strong = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        assert not strong, f"{case['case_id']} 弱信号案例不得含强确认"
        assert result.investigation_checklist, "弱信号必须给出调查清单"
        assert result.false_positive_conditions, "弱信号必须给出误报条件"

    def test_case9_combined_evidence_confirmed(self) -> None:
        case, _, _, result = self._run(9)
        assert result.overall_strength == SignalStrength.IN_SCOPE_CONFIRMED, (
            f"{case['case_id']} 强证据组合应为 IN_SCOPE_CONFIRMED，实际={result.overall_strength}"
        )
        assert result.gate_decision == GateDecision.IN_SCOPE

    def test_case10_ssh_brute_out_of_scope(self) -> None:
        case, _, _, result = self._run(10)
        assert result.overall_strength == SignalStrength.OUT_OF_SCOPE, (
            f"{case['case_id']} SSH 暴力破解应为 OUT_OF_SCOPE，实际={result.overall_strength}"
        )
        ws_evidence = [
            s for s in result.signals
            if s.source in {SignalSource.EVIDENCE, SignalSource.ALERTS} and s.strength in {
                SignalStrength.IN_SCOPE_CONFIRMED, SignalStrength.IN_SCOPE_WEAK
            }
        ]
        assert not ws_evidence, f"{case['case_id']} 证据不得产生 WebShell 范围内信号"
        assert any("Case 10 数据质量问题" in issue for issue in result.input_quality_issues), "Case 10 必须标注 event_type 误标问题"


class TestTask5GateDecision:
    def test_confirmed_webshell_is_in_scope(self) -> None:
        _require_case(9)
        evt = SecurityEventInput.from_dict(_inp(_load_case(9)))
        result = WebShellGatekeeper().audit(evt)
        assert result.gate_decision == GateDecision.IN_SCOPE
        assert result.overall_strength == SignalStrength.IN_SCOPE_CONFIRMED

    def test_weak_webshell_is_weak_signal(self) -> None:
        _require_case(8)
        evt = SecurityEventInput.from_dict(_inp(_load_case(8)))
        result = WebShellGatekeeper().audit(evt)
        assert result.gate_decision == GateDecision.WEAK_SIGNAL

    def test_out_of_scope_is_out_of_scope(self) -> None:
        _require_case(10)
        evt = SecurityEventInput.from_dict(_inp(_load_case(10)))
        result = WebShellGatekeeper().audit(evt)
        assert result.gate_decision == GateDecision.OUT_OF_SCOPE


class TestTask6HandoverAssertions:
    def test_yangjiaqi_three_tier_gate(self) -> None:
        if not all(_case_available(i) for i in (8, 9, 10)):
            pytest.skip("三档门禁案例 case8-10 未随本分支提供（由 PR44 提供）")
        gk = WebShellGatekeeper()
        for idx, expected in ((10, GateDecision.OUT_OF_SCOPE), (8, GateDecision.WEAK_SIGNAL), (9, GateDecision.IN_SCOPE)):
            case = _load_case(idx)
            evt = SecurityEventInput.from_dict(_inp(case))
            result = gk.audit(evt)
            assert result.gate_decision == expected, (
                f"case{idx} 三档判定不符: 期望 {expected.value}, 实际 {result.gate_decision.value}"
            )

    def test_yanyushuo_signal_strength_and_gate(self) -> None:
        if not all(_case_available(i) for i in range(1, 11)):
            pytest.skip("case7-10 由 PR44 提供，本分支未带全套正式案例")
        gk = WebShellGatekeeper()
        expectations = {
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
        for idx, expected in expectations.items():
            case = _load_case(idx)
            evt = SecurityEventInput.from_dict(_inp(case))
            result = gk.audit(evt)
            assert result.overall_strength == expected, (
                f"case{idx} 信号强度不符: 期望 {expected.value}, 实际 {result.overall_strength.value}"
            )

    def test_liyuyan_contract_unified_input(self) -> None:
        if not all(_case_available(i) for i in range(1, 11)):
            pytest.skip("case7-10 由 PR44 提供，本分支未带全套正式案例")
        # 合同读取字段 = 门禁白名单字段；alerts/triage 允许为空或缺失，其余必须出现。
        contract = set(GATEKEEPER_WHITELIST_FIELDS)
        for case in load_all_cases():
            inp_keys = set(_inp(case).keys())
            model_fields = {f.name for f in SecurityEventInput.__dataclass_fields__.values()}
            unknown = inp_keys - model_fields
            assert not unknown, f"{case['case_id']} 含未知字段: {unknown}"
            required = contract - {"alerts", "triage"}
            missing_required = required - inp_keys
            assert not missing_required, f"{case['case_id']} 缺少合同必填字段: {missing_required}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
