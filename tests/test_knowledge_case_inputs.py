# -*- coding: utf-8 -*-
"""T0903-09知识评测案例输入契约测试。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from sec_agent.deep_agent.models import SecurityEventInput


CASE_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "modules"
    / "scenario-knowledge"
    / "knowledge-test-cases"
)


class TestKnowledgeCaseInputs(unittest.TestCase):
    def _load_case(self, number: int) -> tuple[dict, SecurityEventInput]:
        path = CASE_DIR / f"case{number}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload, SecurityEventInput.from_dict(payload)

    def test_all_six_cases_load_with_required_identifiers(self):
        seen_event_ids: set[str] = set()
        seen_trace_ids: set[str] = set()
        seen_run_ids: set[str] = set()

        for number in range(1, 7):
            with self.subTest(case=number):
                payload, event = self._load_case(number)
                self.assertTrue(event.event_id.strip())
                self.assertTrue(event.event_type.strip())
                self.assertTrue(event.trace_id.strip())
                self.assertTrue(event.run_id.strip())
                self.assertIsInstance(event.alerts, list)
                self.assertIsInstance(event.evidence, list)
                self.assertIsInstance(event.triage, dict)
                self.assertIn("verdict", event.triage)
                self.assertIn("confidence", event.triage)

                self.assertEqual(event.event_id, payload["event_id"])
                self.assertEqual(event.event_type, payload["event_type"])
                self.assertEqual(event.trace_id, payload["trace_id"])
                self.assertEqual(event.run_id, payload["run_id"])

                self.assertNotIn(event.event_id, seen_event_ids)
                self.assertNotIn(event.trace_id, seen_trace_ids)
                self.assertNotIn(event.run_id, seen_run_ids)
                seen_event_ids.add(event.event_id)
                seen_trace_ids.add(event.trace_id)
                seen_run_ids.add(event.run_id)

    def test_case6_is_a_pure_non_webshell_negative_input(self):
        payload, event = self._load_case(6)
        searchable_text = json.dumps(payload, ensure_ascii=False).lower()

        self.assertNotIn("webshell", searchable_text)
        self.assertNotIn("web shell", searchable_text)
        self.assertNotIn("网页后门", searchable_text)
        self.assertNotIn("emer-run.php", searchable_text)
        self.assertNotIn("shell.php", searchable_text)
        self.assertNotEqual(event.event_type.lower(), "webshell")

    def test_source_bounded_cases_do_not_reintroduce_unsupported_claims(self):
        case1_payload, _ = self._load_case(1)
        case2_payload, _ = self._load_case(2)
        case1_text = json.dumps(case1_payload, ensure_ascii=False).lower()
        case2_text = json.dumps(case2_payload, ensure_ascii=False).lower()

        self.assertNotIn("aes", case1_text)
        for unsupported in (
            "godzilla",
            "哥斯拉",
            "machinekey",
            "viewstate",
            "wingtb",
            "rootkit",
        ):
            with self.subTest(term=unsupported):
                self.assertNotIn(unsupported, case2_text)
        self.assertIn("尚无证据证明webshell部署成功", case2_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
