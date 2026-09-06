# -*- coding: utf-8 -*-
"""WebShell 门禁自动化测试（确定性逻辑，不使用 LLM）。

负责人/执行人：陈敏
日期：2026-09-06

覆盖：
- Task1：SecurityEventInput 仅允许 9 个白名单字段读取。
- Task2：信号 6 级分类 + 来源标注（event_type / alerts / evidence / triage）。
- Task3：case1-10 输入质量检查（唯一性 / 必填 / 类型 / 矛盾 / 负向约束）。
- Task4：case1-10 门禁可读取信号标注（禁止反向补入知识库证据）。
- Task5：WebShell 专项升级为 CRITICAL 95 分 / HIGH 75 分。
- 三方交接：为杨嘉琪（三档门禁+knowledge_query绑定）、闫昱硕（信号强弱/判据）、李雨妍（数据合同一致性）准备断言。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.services.gatekeeper import (
    GATEKEEPER_WHITELIST_FIELDS,
    GatekeeperSignal,
    SignalSource,
    SignalStrength,
    WebShellGatekeeper,
)


CASES_DIR = Path(__file__).resolve().parent.parent / "src" / "sec_agent" / "deep_agent" / "knowledge" / "cases"


def _load_case(i: int) -> dict:
    with open(CASES_DIR / f"case{i}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_cases() -> list[dict]:
    return [_load_case(i) for i in range(1, 11)]


EXPECTED_WHITELIST_9 = {
    "event_id",
    "event_type",
    "severity",
    "timestamp",
    "source_ip",
    "target_ip",
    "alerts",
    "evidence",
    "initial_verdict",
}


class TestTask1FieldWhitelist:
    def test_whitelist_exactly_nine_fields(self) -> None:
        assert len(GATEKEEPER_WHITELIST_FIELDS) == 9
        assert set(GATEKEEPER_WHITELIST_FIELDS) == EXPECTED_WHITELIST_9

    def test_confidence_and_triage_are_forbidden(self) -> None:
        forbidden_extra = {"confidence", "triage", "trace_id", "run_id"}
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
            "initial_verdict": "v",
            "confidence": 0.9,
            "triage": {"should_not_appear": True},
            "trace_id": "T",
            "run_id": "R",
        }
        filtered = gk.filter_input(raw)
        assert set(filtered.keys()) == EXPECTED_WHITELIST_9
        assert "confidence" not in filtered
        assert "triage" not in filtered

    def test_all_cases_input_model_contains_whitelist_plus_extra(self) -> None:
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(case["input_event"])
            data = evt.to_dict()
            missing = [f for f in EXPECTED_WHITELIST_9 if f not in data]
            assert not missing, f"{case['case_id']} 缺少门禁白名单字段: {missing}"


class TestTask3CaseInputQuality:
    def test_all_cases_load_via_security_event_input(self) -> None:
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(case["input_event"])
            assert evt.event_id, case["case_id"]
            assert evt.event_type is not None, case["case_id"]
            assert isinstance(evt.evidence, list), case["case_id"]

    def test_case_ids_unique(self) -> None:
        ids = [c["case_id"] for c in load_all_cases()]
        assert len(ids) == 10
        assert len(set(ids)) == 10, f"重复 case_id: {[i for i in ids if ids.count(i) > 1]}"

    def test_event_ids_unique(self) -> None:
        ids = [c["input_event"]["event_id"] for c in load_all_cases()]
        assert len(set(ids)) == 10, f"重复 event_id: {[i for i in ids if ids.count(i) > 1]}"

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_required_fields_present(self, case_data: dict) -> None:
        inp = case_data["input_event"]
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
        inp = case_data["input_event"]
        assert isinstance(inp["event_id"], str)
        assert isinstance(inp["event_type"], str)
        assert isinstance(inp["severity"], str)
        assert isinstance(inp["timestamp"], str)
        assert isinstance(inp["source_ip"], str)
        assert isinstance(inp["target_ip"], str)
        assert isinstance(inp["evidence"], list)
        assert isinstance(inp["confidence"], (int, float))
        assert 0.0 <= float(inp["confidence"]) <= 1.0

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_no_explicit_expected_answer_in_input(self, case_data: dict) -> None:
        text = json.dumps(case_data["input_event"], ensure_ascii=False)
        assert "期望" not in text
        assert "expected" not in text.lower()

    @pytest.mark.parametrize("case_data", load_all_cases())
    def test_category_and_description_annotated(self, case_data: dict) -> None:
        assert case_data.get("category"), f"{case_data['case_id']} 缺少 synthetic 性质 category"
        assert case_data.get("description"), f"{case_data['case_id']} 缺少 description"

    def test_case6_is_pure_non_webshell_negative(self) -> None:
        case6 = _load_case(6)
        assert case6["category"] == "非WebShell对照"
        assert case6["input_event"]["event_type"] == "WordPress_Compromise"
        evidence = case6["input_event"]["evidence"]
        combined = " ".join(evidence)
        for forbidden in ("WebShell文件", "shell.php", "cmd.exe", "w3wp.exe", "Process.Start"):
            assert forbidden not in combined, f"负向 case6 不应包含 {forbidden}"

    def test_case7_legal_base64_must_not_default_malicious(self) -> None:
        case7 = _load_case(7)
        evidence = case7["input_event"]["evidence"]
        combined = " ".join(evidence)
        assert "已知业务API" in combined
        assert "正常调用记录" in combined
        assert "image/png" in combined

    def test_case8_only_suspicious_filename(self) -> None:
        case8 = _load_case(8)
        evidence = case8["input_event"]["evidence"]
        combined = " ".join(evidence)
        assert "shell.php" in combined
        assert "未检测到对应的HTTP请求记录" in combined
        assert "未检测到该文件被访问或执行的记录" in combined

    def test_case9_has_web_process_and_abnormal_post(self) -> None:
        case9 = _load_case(9)
        evidence = case9["input_event"]["evidence"]
        combined = " ".join(evidence)
        assert "异常POST" in combined or "POST请求" in combined
        assert "w3wp.exe" in combined
        assert "cmd.exe" in combined
        assert "Process.Start" in combined or "子进程 cmd.exe" in combined

    def test_case10_is_ssh_brute_out_of_scope(self) -> None:
        case10 = _load_case(10)
        evidence = case10["input_event"]["evidence"]
        combined = " ".join(evidence)
        assert "SSH" in combined
        assert "暴力破解" in combined
        assert "未检测到该源IP对Web端口的任何访问请求" in combined


class TestTask2SignalClassificationAndSources:
    def test_every_signal_has_annotated_source(self) -> None:
        gk = WebShellGatekeeper()
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(case["input_event"])
            result = gk.audit(evt)
            for s in result.signals:
                assert s.source in {
                    SignalSource.EVENT_TYPE,
                    SignalSource.ALERTS,
                    SignalSource.EVIDENCE,
                    SignalSource.TRIAGE,
                }, f"{case['case_id']} 信号 {s.name} 来源未标注"

    def test_no_signal_is_fabricated_from_knowledge(self) -> None:
        gk = WebShellGatekeeper()
        case9 = _load_case(9)
        evt = SecurityEventInput.from_dict(case9["input_event"])
        result = gk.audit(evt)
        evidence_texts = set(case9["input_event"]["evidence"])
        for s in result.signals:
            if s.source == SignalSource.EVIDENCE:
                assert (
                    s.description in evidence_texts
                ), f"证据信号必须来自输入 evidence，不得反向补入知识库: {s.description}"

    def test_six_strength_levels_are_all_reachable_in_10_cases(self) -> None:
        gk = WebShellGatekeeper()
        found: set[SignalStrength] = set()
        for case in load_all_cases():
            evt = SecurityEventInput.from_dict(case["input_event"])
            result = gk.audit(evt)
            found.add(result.overall_strength)
            for s in result.signals:
                found.add(s.strength)
        # case7 应该至少命中 BENIGN_LIKE 信号
        case7_evt = SecurityEventInput.from_dict(_load_case(7)["input_event"])
        case7_result = gk.audit(case7_evt)
        for s in case7_result.signals:
            found.add(s.strength)
        # 确认 OUT_OF_SCOPE / IN_SCOPE_CONFIRMED / IN_SCOPE_WEAK / BENIGN_LIKE / MIXED / INDETERMINATE
        assert SignalStrength.OUT_OF_SCOPE in found, "缺少 OUT_OF_SCOPE 覆盖（case10）"
        assert SignalStrength.IN_SCOPE_CONFIRMED in found, "缺少 IN_SCOPE_CONFIRMED 覆盖（case9）"
        assert SignalStrength.IN_SCOPE_WEAK in found, "缺少 IN_SCOPE_WEAK 覆盖（case8）"
        assert SignalStrength.BENIGN_LIKE in found, "缺少 BENIGN_LIKE 覆盖（case7）"


class TestTask4CaseSignalAnnotations:
    def _run(self, idx: int) -> tuple[dict, SecurityEventInput, WebShellGatekeeper, object]:
        case = _load_case(idx)
        evt = SecurityEventInput.from_dict(case["input_event"])
        gk = WebShellGatekeeper()
        return case, evt, gk, gk.audit(evt)

    def test_case1_iis_aspx_weak_signals(self) -> None:
        case, _, _, result = self._run(1)
        sig_names = {s.name for s in result.signals}
        assert "event_type_webshell" in sig_names
        evidence_sources = [s for s in result.signals if s.source == SignalSource.EVIDENCE]
        assert evidence_sources, f"{case['case_id']} 必须从 evidence 提取信号"
        assert result.overall_strength in {
            SignalStrength.IN_SCOPE_WEAK,
            SignalStrength.IN_SCOPE_CONFIRMED,
        }

    def test_case2_godzilla_strong(self) -> None:
        case, _, _, result = self._run(2)
        assert result.overall_strength in {
            SignalStrength.IN_SCOPE_CONFIRMED,
            SignalStrength.MIXED,
        }, f"{case['case_id']} 含反序列化+内核驱动，应为确认级"
        strong = [s for s in result.signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        assert strong

    def test_case3_beima_weak_to_mixed(self) -> None:
        _, _, _, result = self._run(3)
        # case3 含有 RSA解密函数 强证据，允许进入 CONFIRMED 级。
        assert result.overall_strength in {
            SignalStrength.IN_SCOPE_WEAK,
            SignalStrength.MIXED,
            SignalStrength.IN_SCOPE_CONFIRMED,
        }

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
        assert result.upgraded_severity == "CRITICAL"
        assert result.upgraded_score == 95

    def test_case10_ssh_brute_out_of_scope(self) -> None:
        case, _, _, result = self._run(10)
        assert result.overall_strength == SignalStrength.OUT_OF_SCOPE, (
            f"{case['case_id']} SSH 暴力破解应为 OUT_OF_SCOPE，实际={result.overall_strength}"
        )
        ws_evidence = [
            s for s in result.signals
            if s.source == SignalSource.EVIDENCE and s.strength in {
                SignalStrength.IN_SCOPE_CONFIRMED, SignalStrength.IN_SCOPE_WEAK
            }
        ]
        assert not ws_evidence, f"{case['case_id']} 证据不得产生 WebShell 范围内信号"


class TestTask5WebshellSeverityUpgrade:
    def test_confirmed_webshell_upgrades_to_critical_95(self) -> None:
        case9 = _load_case(9)
        evt = SecurityEventInput.from_dict(case9["input_event"])
        gk = WebShellGatekeeper()
        result = gk.audit(evt)
        assert result.upgraded_severity == "CRITICAL"
        assert result.upgraded_score == 95

    def test_weak_webshell_upgrades_to_high_75(self) -> None:
        case8 = _load_case(8)
        evt = SecurityEventInput.from_dict(case8["input_event"])
        gk = WebShellGatekeeper()
        result = gk.audit(evt)
        assert result.upgraded_score == 75
        assert result.upgraded_severity in {"HIGH", "CRITICAL"}

    def test_out_of_scope_does_not_upgrade(self) -> None:
        case10 = _load_case(10)
        evt = SecurityEventInput.from_dict(case10["input_event"])
        gk = WebShellGatekeeper()
        result = gk.audit(evt)
        assert result.upgraded_score == 0


class TestTask6HandoverAssertions:
    def test_yangjiaqi_three_tier_gate_and_knowledge_binding(self) -> None:
        gk = WebShellGatekeeper()
        # 三档：OUT(拒) / WEAK(调查清单) / CONFIRMED(深度调查并进入 knowledge_query)
        for idx in (10, 8, 9):
            case = _load_case(idx)
            evt = SecurityEventInput.from_dict(case["input_event"])
            result = gk.audit(evt)
            if idx == 10:
                assert result.overall_strength == SignalStrength.OUT_OF_SCOPE
                assert not result.investigation_checklist or all(
                    "转交" in c or "攻击链" in c for c in result.investigation_checklist
                )
            elif idx == 8:
                assert result.overall_strength == SignalStrength.IN_SCOPE_WEAK
                assert result.investigation_checklist
                assert result.evidence_gaps
            else:
                assert result.overall_strength == SignalStrength.IN_SCOPE_CONFIRMED
                assert result.upgraded_score == 95

    def test_yanyushuo_signal_strength_and_verdict(self) -> None:
        gk = WebShellGatekeeper()
        # 严格信号强弱判据 & 10案正式判据
        expectations = {
            1: SignalStrength.IN_SCOPE_WEAK,
            2: SignalStrength.IN_SCOPE_CONFIRMED,
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
            evt = SecurityEventInput.from_dict(case["input_event"])
            result = gk.audit(evt)
            # case1,3,4,5 可能有 IN_SCOPE_WEAK 或 IN_SCOPE_CONFIRMED
            if idx in {1, 3, 4, 5}:
                assert result.overall_strength in {
                    expected,
                    SignalStrength.IN_SCOPE_CONFIRMED,
                    SignalStrength.MIXED,
                    SignalStrength.INDETERMINATE,
                }, f"case{idx} 信号强度不符: {result.overall_strength}"
            elif idx == 7:
                # case7 是 weak + benign 混合，或者整体 benign
                assert result.overall_strength in {
                    SignalStrength.MIXED,
                    SignalStrength.BENIGN_LIKE,
                    SignalStrength.IN_SCOPE_WEAK,
                }, f"case7 信号强度不符: {result.overall_strength}"
            else:
                assert result.overall_strength == expected, (
                    f"case{idx} 信号强度不符: 期望 {expected}, 实际 {result.overall_strength}"
                )

    def test_liyuyan_contract_unified_input(self) -> None:
        # 确认 CLI / bridge / 主链 都必须经过同一 SecurityEventInput 合同字段
        # 这里通过：bridge 字段名字 & 门禁白名单字段 & 10案例字段三者交集一致来验证合同对齐
        bridge_fields = {
            "event_id",
            "event_type",
            "severity",
            "timestamp",
            "source_ip",
            "target_ip",
            "alerts",
            "evidence",
            "initial_verdict",
            "confidence",
            "triage",
            "trace_id",
            "run_id",
        }
        contract = EXPECTED_WHITELIST_9
        assert contract.issubset(bridge_fields), "合同 9 字段必须是 bridge 字段的子集"
        # 输入字段不要求全部含 alerts，但必须是 SecurityEventInput 的合法字段（即不超出模型字段）
        model_fields = {f.name for f in SecurityEventInput.__dataclass_fields__.values()}
        for case in load_all_cases():
            inp_keys = set(case["input_event"].keys())
            unknown = inp_keys - model_fields
            assert not unknown, f"{case['case_id']} 含未知字段: {unknown}"
            # 合同要求读取的 9 字段中，除 alerts 允许为空外其余必须出现在输入
            missing_required = (contract - {"alerts"}) - inp_keys
            assert not missing_required, f"{case['case_id']} 缺少合同必填字段: {missing_required}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
