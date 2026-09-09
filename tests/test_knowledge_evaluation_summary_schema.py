# -*- coding: utf-8 -*-
"""知识评测汇总 Schema 与最小 fixture 结构守护测试。"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "evaluation"
SCHEMA_PATH = FIXTURE_DIR / "knowledge_evaluation_summary.schema.json"
SUMMARY_PATH = FIXTURE_DIR / "minimal_knowledge_evaluation_summary.json"

SCHEMA_VERSION = "2026-09-06.knowledge-eval-summary.v1"

RESULT_REQUIRED_KEYS = {
    "case_id",
    "knowledge_mode",
    "applicability",
    "matched_knowledge_ids",
    "tool_status",
    "evidence_refs",
    "forbidden_conclusion_hit",
    "manual_takeover",
    "step_count",
    "duration_ms",
    "human_review",
}

KNOWLEDGE_MODES = {
    "knowledge_required",
    "knowledge_optional",
    "knowledge_forbidden",
    "knowledge_not_applicable",
}

APPLICABILITY_VALUES = {
    "applicable",
    "partially_applicable",
    "not_applicable",
    "unknown",
}

KNOWLEDGE_IDS = {
    "K-WEBSHELL-PRINCIPLE",
    "K-WEBSHELL-FEATURES",
    "K-WEBSHELL-TOOLS-TRAFFIC",
    "K-WEBSHELL-EVIDENCE-CHECKLIST",
    "K-WEBSHELL-RESPONSE-TEMPLATE",
    "K-WEBSHELL-MANUAL-TAKEOVER",
}

TOOL_STATES = {
    "success",
    "failed",
    "partial",
    "not_called",
    "skipped",
}

HUMAN_REVIEW_KEYS = {
    "status",
    "reviewer",
    "reviewed_at",
    "comments",
    "action_items",
}

HUMAN_REVIEW_STATUSES = {
    "pending",
    "passed",
    "failed",
    "needs_follow_up",
}


class TestKnowledgeEvaluationSummarySchema(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_schema_freezes_required_result_fields(self) -> None:
        result_schema = self.schema["$defs"]["evaluation_result"]

        self.assertEqual(set(result_schema["required"]), RESULT_REQUIRED_KEYS)
        self.assertFalse(result_schema["additionalProperties"])
        self.assertEqual(
            result_schema["properties"]["knowledge_mode"]["enum"],
            [
                "knowledge_required",
                "knowledge_optional",
                "knowledge_forbidden",
                "knowledge_not_applicable",
            ],
        )
        self.assertEqual(
            result_schema["properties"]["human_review"]["description"],
            "人工 Review 栏。",
        )

    def test_minimal_fixture_matches_frozen_contract(self) -> None:
        self.assertEqual(self.summary["schema_version"], SCHEMA_VERSION)
        self.assertRegex(self.summary["evaluation_id"], r"^eval-[0-9]{8}-[a-z0-9-]+$")
        self.assertEqual(self.summary["suite"]["case_count"], len(self.summary["results"]))

        seen_cases: set[str] = set()
        for result in self.summary["results"]:
            with self.subTest(case_id=result.get("case_id")):
                self._assert_result_contract(result)
                self.assertNotIn(result["case_id"], seen_cases)
                seen_cases.add(result["case_id"])

    def test_minimal_fixture_covers_core_evaluation_paths(self) -> None:
        by_case = {result["case_id"]: result for result in self.summary["results"]}

        self.assertEqual(by_case["case1"]["knowledge_mode"], "knowledge_required")
        self.assertTrue(by_case["case1"]["matched_knowledge_ids"])
        self.assertTrue(by_case["case5"]["manual_takeover"])
        self.assertEqual(by_case["case5"]["tool_status"]["mcp_tools"], "failed")
        self.assertEqual(by_case["case6"]["knowledge_mode"], "knowledge_forbidden")
        self.assertEqual(by_case["case6"]["matched_knowledge_ids"], [])
        self.assertFalse(by_case["case6"]["forbidden_conclusion_hit"])

    def _assert_result_contract(self, result: dict[str, Any]) -> None:
        self.assertEqual(set(result), RESULT_REQUIRED_KEYS)
        self.assertRegex(result["case_id"], r"^(case[1-9][0-9]*|TC-[A-Z0-9-]+)$")
        self.assertIn(result["knowledge_mode"], KNOWLEDGE_MODES)
        self.assertIn(result["applicability"], APPLICABILITY_VALUES)
        self.assertIsInstance(result["forbidden_conclusion_hit"], bool)
        self.assertIsInstance(result["manual_takeover"], bool)
        self.assertIsInstance(result["step_count"], int)
        self.assertGreaterEqual(result["step_count"], 0)
        self.assertIsInstance(result["duration_ms"], int)
        self.assertGreaterEqual(result["duration_ms"], 0)

        self.assertEqual(len(result["matched_knowledge_ids"]), len(set(result["matched_knowledge_ids"])))
        for knowledge_id in result["matched_knowledge_ids"]:
            self.assertIn(knowledge_id, KNOWLEDGE_IDS)

        tool_status = result["tool_status"]
        self.assertEqual(set(tool_status), {"knowledge_query", "mcp_tools", "notes"})
        self.assertIn(tool_status["knowledge_query"], TOOL_STATES)
        self.assertIn(tool_status["mcp_tools"], TOOL_STATES)
        self.assertIsInstance(tool_status["notes"], str)

        self.assertEqual(len(result["evidence_refs"]), len(set(result["evidence_refs"])))
        for evidence_ref in result["evidence_refs"]:
            self.assertIsInstance(evidence_ref, str)
            self.assertTrue(evidence_ref.strip())

        human_review = result["human_review"]
        self.assertEqual(set(human_review), HUMAN_REVIEW_KEYS)
        self.assertIn(human_review["status"], HUMAN_REVIEW_STATUSES)
        self.assertTrue(human_review["reviewer"] is None or isinstance(human_review["reviewer"], str))
        self.assertTrue(human_review["reviewed_at"] is None or re.match(r"^\\d{4}-\\d{2}-\\d{2}T", human_review["reviewed_at"]))
        self.assertIsInstance(human_review["comments"], str)
        self.assertIsInstance(human_review["action_items"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
