# -*- coding: utf-8 -*-
"""知识包检索工具（knowledge.query）测试。

运行（在项目根目录，需 src 在导入路径上）：
  PYTHONPATH=src python -m unittest tests.test_knowledge_tool -v
"""
from __future__ import annotations

import unittest

from sec_agent.deep_agent.tools.base import ToolRegistry
from sec_agent.deep_agent.tools.knowledge import (
    build_knowledge_tools,
    load_knowledge_entries,
    match_keyword,
)


class TestKnowledgeEntries(unittest.TestCase):
    def test_entries_loaded(self):
        entries = load_knowledge_entries()
        names = {e.name for e in entries}
        # 知识包核心章节都应解析为条目
        for expected in ["攻击原理", "攻击特征速查表", "主流管理工具与流量特征", "证据检查清单", "处置建议模板"]:
            self.assertIn(expected, names)

    def test_attack_principle_content_not_empty(self):
        entries = {e.name: e for e in load_knowledge_entries()}
        self.assertTrue(entries["攻击原理"].content)
        self.assertTrue(entries["处置建议模板"].content)


class TestKeywordMatch(unittest.TestCase):
    def setUp(self):
        self.entries = load_knowledge_entries()

    def test_match_attack_principle(self):
        self.assertEqual(match_keyword(self.entries, "WebShell攻击原理").name, "攻击原理")

    def test_match_disposal(self):
        self.assertEqual(match_keyword(self.entries, "WebShell处置建议").name, "处置建议模板")

    def test_match_tool_traffic(self):
        self.assertEqual(match_keyword(self.entries, "中国菜刀 流量特征").name, "主流管理工具与流量特征")

    def test_match_checklist(self):
        self.assertEqual(match_keyword(self.entries, "证据检查清单").name, "证据检查清单")

    def test_match_manual_takeover(self):
        self.assertEqual(match_keyword(self.entries, "人工接管").name, "停止条件与人工接管规则")

    def test_no_match(self):
        self.assertIsNone(match_keyword(self.entries, "如何做午饭"))
        self.assertIsNone(match_keyword(self.entries, "  "))


class TestKnowledgeQueryTool(unittest.TestCase):
    def setUp(self):
        self.tool = build_knowledge_tools()[0]

    def test_schema_ascii_and_name(self):
        schema = self.tool.to_openai_schema()
        self.assertEqual(schema["function"]["name"], "knowledge_query")
        self.assertRegex(schema["function"]["name"], r"^[a-zA-Z0-9_-]+$")

    def test_hit_returns_evidence_refs(self):
        result = self.tool.call({"keyword": "WebShell处置建议"})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["entry"], "处置建议模板")
        self.assertTrue(result.data["evidence_refs"])
        self.assertIn("CISA", result.data["evidence_refs"][0])
        # summary 里同时带 evidence_refs，供 LLM 直接读
        self.assertIn("evidence_refs", result.summary)

    def test_attack_principle_evidence_ref(self):
        result = self.tool.call({"keyword": "WebShell攻击原理"})
        self.assertEqual(result.status, "success")
        self.assertTrue(any("T1505.003" in ref for ref in result.data["evidence_refs"]))

    def test_miss_returns_failed(self):
        result = self.tool.call({"keyword": "不存在的关键词"})
        self.assertEqual(result.status, "failed")

    def test_registered_in_registry(self):
        reg = ToolRegistry()
        for t in build_knowledge_tools():
            reg.register(t)
        names = [s["function"]["name"] for s in reg.schemas()]
        self.assertIn("knowledge_query", names)
        self.assertEqual(len(names), len(set(names)))
        self.assertRegex(names[0], r"^[a-zA-Z0-9_-]+$")


# 问答样本覆盖验证（对应《问答样本示例_v1.md》5 题的知识包检索可达性）
class TestKnowledgeQaCoverage(unittest.TestCase):
    """评测知识包对问答样本的检索覆盖：命中到哪个条目 / 是否缺知识。

    预期（当前知识包范围）：
      - 样本 1（ATT&CK 战术 / T1505.003）→ 攻击原理（含 T1505.003 引用）；
      - 样本 2（列举攻击组织）→ 知识包无此章节，应返回 None（覆盖缺口）；
      - 样本 3（检测策略 DET0394）→ 部分覆盖：命中证据检查清单（检查项），不含 DET0394 细节；
      - 样本 4（检测方法）→ 命中证据检查清单；
      - 样本 5（消除流程）→ 命中处置建议模板（CISA CM0106 完全覆盖）。
    """

    def setUp(self):
        self.entries = load_knowledge_entries()

    def test_sample1_attack_framework(self):
        entry = match_keyword(self.entries, "WebShell 攻击原理 MITRE ATT&CK 技术编号")
        self.assertEqual(entry.name, "攻击原理")

    def test_sample2_attack_groups_is_gap(self):
        entry = match_keyword(self.entries, "使用过 WebShell 的攻击组织")
        self.assertIsNone(entry)  # 当前知识包未覆盖攻击组织章节

    def test_sample3_detection_strategy_partial(self):
        entry = match_keyword(self.entries, "检测WebShell的服务器行为")
        self.assertEqual(entry.name, "证据检查清单")  # 部分命中（检查项清单）；DET0394 详细策略未覆盖

    def test_sample4_detection_methods(self):
        entry = match_keyword(self.entries, "WebShell检测方法")
        self.assertEqual(entry.name, "证据检查清单")

    def test_sample5_elimination_flow(self):
        entry = match_keyword(self.entries, "发现 WebShell 后的消除流程")
        self.assertEqual(entry.name, "处置建议模板")


if __name__ == "__main__":
    unittest.main(verbosity=2)
