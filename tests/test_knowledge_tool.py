# -*- coding: utf-8 -*-
"""知识包检索工具（knowledge.query）测试。

运行（在项目根目录，需 src 在导入路径上）：
  PYTHONPATH=src python -m unittest tests.test_knowledge_tool -v
"""
from __future__ import annotations

import unittest

from sec_agent.deep_agent.tools.base import ToolRegistry
from sec_agent.deep_agent.tools.knowledge import (
    _default_knowledge_text,
    build_knowledge_tools,
    match_knowledge_card,
    parse_knowledge_cards,
)


class TestKnowledgeCards(unittest.TestCase):
    def setUp(self):
        self.cards = parse_knowledge_cards(_default_knowledge_text())

    def test_all_structured_cards_are_loaded(self):
        self.assertEqual(len(self.cards), 15)
        self.assertEqual(len({card.knowledge_id for card in self.cards}), 15)
        for card in self.cards:
            self.assertTrue(card.topic)
            self.assertTrue(card.required_evidence)
            self.assertTrue(card.source_urls)

    def test_match_by_exact_id(self):
        self.assertEqual(match_knowledge_card(self.cards, "WSK-004").knowledge_id, "WSK-004")

    def test_match_by_exact_topic(self):
        topic = self.cards[5].topic
        self.assertEqual(match_knowledge_card(self.cards, topic).knowledge_id, "WSK-006")

    def test_match_by_controlled_alias(self):
        self.assertEqual(match_knowledge_card(self.cards, "WebShell攻击原理").knowledge_id, "WSK-001")
        self.assertEqual(match_knowledge_card(self.cards, "WebShell证据检查清单").knowledge_id, "WSK-010")
        self.assertEqual(match_knowledge_card(self.cards, "WebShell人工接管条件").knowledge_id, "WSK-011")
        self.assertEqual(match_knowledge_card(self.cards, "WebShell处置建议").knowledge_id, "WSK-015")

    def test_match_when_topic_is_contained_in_query(self):
        query = f"请查询：{self.cards[12].topic}"
        self.assertEqual(match_knowledge_card(self.cards, query).knowledge_id, "WSK-013")

    def test_no_match(self):
        self.assertIsNone(match_knowledge_card(self.cards, "如何做午饭"))
        self.assertIsNone(match_knowledge_card(self.cards, "  "))

    def test_unsupported_attack_group_query_remains_a_gap(self):
        self.assertIsNone(match_knowledge_card(self.cards, "使用过 WebShell 的攻击组织"))


class TestKnowledgeQueryTool(unittest.TestCase):
    def setUp(self):
        self.tool = build_knowledge_tools(gate_decision="in_scope")[0]

    def test_schema_ascii_and_name(self):
        schema = self.tool.to_openai_schema()
        self.assertEqual(schema["function"]["name"], "knowledge_query")
        self.assertRegex(schema["function"]["name"], r"^[a-zA-Z0-9_-]+$")

    def test_hit_returns_structured_card(self):
        result = self.tool.call({"keyword": "WebShell处置建议"})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["knowledge_id"], "WSK-015")
        self.assertTrue(result.data["required_evidence"])
        self.assertTrue(result.data["prohibited_inference"])
        self.assertTrue(result.data["source_citations"]["urls"])
        self.assertTrue(result.data["source_citations"]["levels"])

    def test_attack_principle_source_citation(self):
        result = self.tool.call({"keyword": "WebShell攻击原理"})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["knowledge_id"], "WSK-001")
        self.assertTrue(
            any(
                "attack.mitre.org" in ref
                for ref in result.data["source_citations"]["urls"]
            )
        )

    def test_miss_returns_failed(self):
        result = self.tool.call({"keyword": "不存在的关键词"})
        self.assertEqual(result.status, "failed")

    def test_registered_in_registry(self):
        reg = ToolRegistry()
        for t in build_knowledge_tools(gate_decision="in_scope"):
            reg.register(t)
        names = [s["function"]["name"] for s in reg.schemas()]
        self.assertIn("knowledge_query", names)
        self.assertEqual(len(names), len(set(names)))
        self.assertRegex(names[0], r"^[a-zA-Z0-9_-]+$")

if __name__ == "__main__":
    unittest.main(verbosity=2)
