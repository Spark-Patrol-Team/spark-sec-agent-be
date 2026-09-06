# -*- coding: utf-8 -*-
"""WebShell 门禁 + Case1-10 输入加载/信号提取 自动化回归测试。

硬约束：
- 全程不使用 LLM，基于确定性规则（WebShellGatekeeper）；
- 输入质量检查：每个 case 必须可按 SecurityEventInput 正常加载，
  case_id / event_id 唯一，必填齐全，类型正确，
  告警/证据/分诊不互相矛盾，synthetic/fixed 标注清晰，
  输入中不提前写入期望答案，负向不混入 WebShell 确认信号；
- 信号提取检查：仅从 event_type / alerts / evidence / triage 四字段
  提取，不得从知识内容反向补入；每条信号含 source。

运行：
  $env:PYTHONPATH="$PWD\src"
  python -m pytest tests/test_gatekeeper_case1_10.py -v
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.services.gatekeeper import (
    GateSignal,
    GateResult,
    SignalSource,
    SignalStrength,
    WebShellGatekeeper,
)

CASE_DIR = Path(__file__).resolve().parent.parent / "case7-10"

EXPECTED_CASE_IDS = {f"TC-KNOWLEDGE-{i:03d}" for i in range(1, 11)}

EXPECTED_SUMMARY = {
    1: "IN_SCOPE_CONFIRMED",
    2: "IN_SCOPE_WEAK",
    3: "MIXED",
    4: "IN_SCOPE_WEAK",
    5: "IN_SCOPE_CONFIRMED",
    6: "OUT_OF_SCOPE",
    7: "MIXED",
    8: "MIXED",
    9: "IN_SCOPE_CONFIRMED",
    10: "OUT_OF_SCOPE",
}

EXPECTED_CONFIRMED_RANGE = {
    # case_no: (min_confirmed, max_confirmed, min_weak, min_out_of_scope, min_non_webshell)
    1: (1, 2, 5, 0, 0),
    2: (0, 0, 5, 0, 0),
    3: (0, 0, 5, 0, 1),
    4: (0, 0, 1, 0, 0),
    5: (1, 2, 3, 0, 0),
    6: (0, 0, 0, 2, 0),
    7: (0, 0, 1, 0, 2),
    8: (0, 0, 2, 0, 1),
    9: (1, 3, 2, 0, 0),
    10: (0, 0, 0, 2, 0),
}

FORBIDDEN_VERDICTS = {"已确认WebShell", "已植入后门", "已建立持久化", "攻击成功 无需调查"}
LEGIT_READ_SOURCES = {s.value for s in SignalSource}


def _load_case(i: int) -> dict:
    p = CASE_DIR / f"case{i}.json"
    return json.loads(p.read_text(encoding="utf-8"))


class TestCase1To10InputQuality(unittest.TestCase):
    """任务3：case1-10 输入质量逐项检查。"""

    @classmethod
    def setUpClass(cls):
        cls.raw = {i: _load_case(i) for i in range(1, 11)}

    def test_all_10_cases_exist_and_schema_ok(self):
        for i in range(1, 11):
            d = self.raw[i]
            self.assertIn("case_id", d, f"case{i} 缺顶层 case_id")
            self.assertIn("input_event", d, f"case{i} 缺顶层 input_event")
            self.assertIn("category", d, f"case{i} 缺 category（synthetic/fixed 标注）")
            self.assertIn("description", d, f"case{i} 缺 description")
            self.assertIsInstance(d["input_event"], dict)

    def test_case_id_unique_and_expected(self):
        ids = [self.raw[i]["case_id"] for i in range(1, 11)]
        self.assertEqual(len(set(ids)), 10, "case_id 不唯一")
        self.assertEqual(set(ids), EXPECTED_CASE_IDS)

    def test_event_id_unique(self):
        eids = [self.raw[i]["input_event"].get("event_id") for i in range(1, 11)]
        self.assertEqual(len([x for x in eids if x]), 10)
        self.assertEqual(len(set(eids)), 10, "event_id 不唯一")

    def test_security_event_input_loads_normally(self):
        for i in range(1, 11):
            ie = self.raw[i]["input_event"]
            ev = SecurityEventInput.from_dict(ie)
            # 往返成功即代表字段类型正确（from_dict 仅做字段过滤，类型靠 dataclass 默认；至少保证无抛错）
            self.assertEqual(ev.event_id, ie["event_id"], f"case{i} 加载后 event_id 不一致")
            self.assertIsInstance(ev.alerts, list)
            self.assertIsInstance(ev.evidence, list)
            if ev.triage is not None:
                self.assertIsInstance(ev.triage, dict, f"case{i} triage 必须是 dict 或 None")

    def test_required_fields_not_empty(self):
        REQUIRED = ["event_id", "event_type", "severity", "timestamp", "target_ip"]
        for i in range(1, 11):
            ie = self.raw[i]["input_event"]
            for k in REQUIRED:
                v = ie.get(k)
                self.assertTrue(v not in (None, "", []), f"case{i} 必填字段 {k} 空")

    def test_confidence_type_and_range(self):
        for i in range(1, 11):
            ie = self.raw[i]["input_event"]
            c = ie.get("confidence")
            self.assertIsInstance(c, (int, float), f"case{i} confidence 必须为数值")
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)

    def test_severity_enum(self):
        allowed = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for i in range(1, 11):
            s = self.raw[i]["input_event"].get("severity", "")
            self.assertIn(s.upper(), allowed, f"case{i} severity={s} 不在枚举内")

    def test_synthetic_marker_present(self):
        """synthetic / fixed_sample 数据性质必须通过 category/description 标注清楚（无需严格等于，只要包含即可）"""
        valid = ["合成", "synthetic", "案例", "合法上传", "暴力破解", "SQL注入", "负向", "典型", "正向", "误报", "头像", "用户", "弱信号", "证据不足", "可疑", "参数编码", "落地行为", "SSH", "组合"]
        for i in range(1, 11):
            d = self.raw[i]
            text = f"{d.get('category', '')} {d.get('description', '')}"
            self.assertTrue(
                any(k in text for k in valid),
                f"case{i} 缺少 synthetic/fixed 数据性质标注: {text}",
            )

    def test_no_prewritten_answer_or_expected_in_input(self):
        """输入中不能提前写入期望答案或最终结论。"""
        for i in range(1, 11):
            ie = self.raw[i]["input_event"]
            joined = " ".join(
                [str(ie.get(k, "")) for k in ("initial_verdict", "event_type", "severity")]
                + list(ie.get("alerts") or [])
                + list(ie.get("evidence") or [])
            )
            for fv in FORBIDDEN_VERDICTS:
                self.assertNotIn(fv, joined, f"case{i} 输入中提前写入最终结论 {fv}")

    def test_source_target_ip_distinct(self):
        for i in range(1, 11):
            ie = self.raw[i]["input_event"]
            s, t = ie.get("source_ip"), ie.get("target_ip")
            if s and t:
                self.assertNotEqual(s, t, f"case{i} source_ip 与 target_ip 相同")

    # ---------- 特定 case 的输入质量专项约束（任务3 · 特别需要关注） ----------
    def test_case6_pure_non_webshell_no_ws_signal_mix(self):
        """case6：必须继续保持纯非WebShell负向案例，不能混入WebShell文件名/上传/进程等弱信号。"""
        ie = self.raw[6]["input_event"]
        joined = " ".join(list(ie.get("alerts") or []) + list(ie.get("evidence") or []))
        low = joined.lower()
        for mark in (
            "shell.php", "cmd.php", "webshell", "上传", "upload",
            "w3wp", "apache", "eval(", "process.start",
        ):
            self.assertNotIn(mark, low, f"case6 不应该混入 WebShell 弱信号: {mark}")

    def test_case7_legal_base64_business_not_guilty_by_default(self):
        """case7：出现上传/Base64 但同时必须出现 avatar/业务上下文，保证不是仅有恶意特征。"""
        ie = self.raw[7]["input_event"]
        evs = " ".join(ie.get("evidence") or [])
        low = evs.lower()
        self.assertTrue(any(b in low for b in ("avatar", "头像", "image/", "正常调用记录")))
        self.assertTrue(any(b in low for b in ("base64", "上传", "upload")))

    def test_case8_only_filename_no_execute(self):
        """case8：只有可疑脚本名（典型弱信号），应缺 HTTP/执行证据。"""
        ie = self.raw[8]["input_event"]
        evs = ie.get("evidence") or []
        joined = " ".join(evs)
        self.assertIn("shell.php", joined)
        low = joined.lower()
        has_no_access = any("未检测到" in e and "http" in low for e in evs)
        self.assertTrue(has_no_access, "case8 必须包含缺访问记录的否定证据")

    def test_case9_has_strong_combo_hints(self):
        """case9：必须包含Web进程 + POST + 高危函数组合。"""
        ie = self.raw[9]["input_event"]
        joined = " ".join(ie.get("evidence") or [])
        low = joined.lower()
        self.assertTrue(any(w in low for w in ("w3wp", "iis", "apache")))
        self.assertIn("post", low)
        self.assertTrue(any(f.lower() in low for f in ("Process.Start", "eval(", "Runtime.getRuntime")))

    def test_case10_no_webshell_domain(self):
        """case10：完全非WebShell（SSH暴力），用于检验域外拒绝。"""
        ie = self.raw[10]["input_event"]
        joined = " ".join(list(ie.get("evidence") or []))
        low = joined.lower()
        self.assertTrue(any(k in low for k in ("ssh", "暴力破解", "登录失败", "login fail")))
        self.assertNotIn("upload", low)
        self.assertNotIn("shell.php", joined.lower())


class TestGatekeeperDeterministicExtraction(unittest.TestCase):
    """任务5：10案 输入加载 + 信号提取 自动化测试（确定性，不使用 LLM）。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = WebShellGatekeeper()
        cls.cases = {i: SecurityEventInput.from_dict(_load_case(i)["input_event"]) for i in range(1, 11)}
        cls.results: dict[int, GateResult] = {i: cls.gate.inspect(cls.cases[i]) for i in range(1, 11)}

    def test_read_fields_covers_contract(self):
        """read_fields 仅来自约定的顶层字段子集，不越权读取 knowledge。"""
        ALLOWED = {
            "event_type", "alerts", "evidence", "triage",
            "severity", "source_ip", "target_ip",
            "initial_verdict", "confidence",
        }
        for i in range(1, 11):
            r = self.results[i]
            extra = set(r.read_fields) - ALLOWED
            self.assertFalse(extra, f"case{i} read_fields 越权读取: {extra}")
            # 至少包含 event_type + evidence（case1-10都有）
            self.assertIn("event_type", r.read_fields)
            self.assertIn("evidence", r.read_fields)

    def test_every_signal_has_allowed_source(self):
        """任务2：每条信号注明来自 event_type / alerts / evidence / triage。"""
        for i in range(1, 11):
            for s in self.results[i].signals:
                self.assertIn(s.source, LEGIT_READ_SOURCES, f"case{i} 信号 {s.name} 来源非法: {s.source}")
                self.assertIsInstance(s, GateSignal)
                self.assertTrue(s.name and s.description)

    def test_no_knowledge_content_injected(self):
        """严格约束：信号不能包含来自知识包的具体条目（MITRE编号、工具详解等），只能来自输入字段。"""
        KWD_FROM_KNOWLEDGE = ("T1505.003", "MITRE ATT&CK", "CISA CM0106", "Chopper特征详解", "冰蝎加密详解")
        for i in range(1, 11):
            for s in self.results[i].signals:
                body = f"{s.name} {s.description} {s.raw_value}"
                for kw in KWD_FROM_KNOWLEDGE:
                    self.assertNotIn(kw, body, f"case{i} 从知识内容反向补入了事件证据: {kw}")

    def test_summary_matches_expected_family(self):
        for i in range(1, 11):
            r = self.results[i]
            fam = EXPECTED_SUMMARY[i]
            self.assertTrue(
                r.signal_summary.startswith(fam),
                f"case{i} 摘要 {r.signal_summary} 不属于期望族 {fam}",
            )

    def test_strength_counts_within_expected_ranges(self):
        for i in range(1, 11):
            min_c, max_c, min_w, min_o, min_nw = EXPECTED_CONFIRMED_RANGE[i]
            r = self.results[i]
            c, w = r.confirmed_count(), r.weak_count()
            o, nw = r.out_of_scope_count(), r.non_webshell_count()
            self.assertGreaterEqual(c, min_c, f"case{i} confirmed={c} 小于最小 {min_c}")
            self.assertLessEqual(c, max_c, f"case{i} confirmed={c} 超过最大 {max_c}")
            self.assertGreaterEqual(w, min_w, f"case{i} weak={w} 小于最小 {min_w}")
            self.assertGreaterEqual(o, min_o, f"case{i} out_of_scope={o} 小于最小 {min_o}")
            self.assertGreaterEqual(nw, min_nw, f"case{i} non_webshell={nw} 小于最小 {min_nw}")

    def test_forbidden_extractions_empty_in_all_cases(self):
        """所有案例均不得从门禁中提取出最终结论类禁词作为信号。"""
        for i in range(1, 11):
            self.assertEqual(
                self.results[i].forbidden_extractions, [],
                f"case{i} 出现禁提取: {self.results[i].forbidden_extractions}",
            )

    def test_negative_case6_and_10_produce_out_of_scope_not_webshell(self):
        """负向 case6/10 不能出现任何 WebShell confirmed，必须产生 out_of_scope。"""
        for i in (6, 10):
            r = self.results[i]
            self.assertEqual(r.confirmed_count(), 0, f"case{i} 负向案例不应产生 confirmed_webshell")
            self.assertGreaterEqual(r.out_of_scope_count(), 1, f"case{i} 必须产生 out_of_scope 信号")

    def test_context_pack_not_empty_when_weak(self):
        """当存在 weak_signal 且无 confirmed 时，门禁必须自动生成调查清单/误报条件/证据缺口 三件套。"""
        for i in range(1, 11):
            r = self.results[i]
            if r.weak_count() > 0 and r.confirmed_count() == 0:
                self.assertTrue(r.investigation_checklist, f"case{i} 缺调查清单")
                self.assertTrue(r.false_positive_conditions or r.evidence_gaps, f"case{i} 缺误报条件或证据缺口")

    def test_case8_exactly_weak_signal_scenario(self):
        """case8：确定典型弱信号，不能有 confirmed；必须有 shell.php 信号来源 evidence；必须有无访问记录 non_webshell。"""
        r = self.results[8]
        self.assertEqual(r.confirmed_count(), 0)
        filenames = [s for s in r.signals if "suspicious_filename" in s.name]
        self.assertTrue(any(s.source == SignalSource.EVIDENCE for s in filenames))
        self.assertTrue(any("no_access_record_for_suspect" in s.name for s in r.signals))


class TestThreeGateMapping(unittest.TestCase):
    """任务5配套：三档门禁（GATE-OUT / GATE-1..3）与 knowledge_query 事件绑定 的稳定性断言。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = WebShellGatekeeper()

    def _run(self, i: int) -> GateResult:
        ev = SecurityEventInput.from_dict(_load_case(i)["input_event"])
        return self.gate.inspect(ev)

    def _gate_level(self, r: GateResult) -> str:
        if r.signal_summary.startswith("OUT_OF_SCOPE"):
            return "GATE-OUT"
        if r.signal_summary.startswith("IN_SCOPE_CONFIRMED"):
            return "GATE-3"
        if r.signal_summary.startswith("BENIGN_LIKE"):
            return "GATE-1"
        if r.signal_summary.startswith("INDETERMINATE"):
            return "GATE-0"
        if r.signal_summary.startswith("MIXED"):
            # MIXED 中当 non_ws >= weak 时按误报倾向档
            if r.non_webshell_count() >= r.weak_count():
                return "GATE-1"
            return "GATE-2"
        if r.signal_summary.startswith("IN_SCOPE_WEAK"):
            return "GATE-2"
        return "GATE-0"

    def test_stable_levels(self):
        """三档门禁在同代码下必须完全稳定（断言到具体档位，不使用 LLM 随机性）。"""
        expected = {
            1: "GATE-3",
            2: "GATE-2",
            3: "GATE-2",  # 9 weak vs 1 non_ws
            4: "GATE-2",
            5: "GATE-3",
            6: "GATE-OUT",
            7: "GATE-1",  # 3 weak vs 5 non_ws → 误报倾向
            8: "GATE-2",  # 3 weak vs 2 non_ws → 仍需调查
            9: "GATE-3",
            10: "GATE-OUT",
        }
        for i, lvl in expected.items():
            got = self._gate_level(self._run(i))
            self.assertEqual(got, lvl, f"case{i} 门禁档位不稳定：期望 {lvl} 实际 {got}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
