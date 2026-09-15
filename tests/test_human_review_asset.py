from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = REPO_ROOT / "eval_results" / "spark-eval-actual-package" / "_human_review.json"


def _payload() -> dict:
    return json.loads(REVIEW_PATH.read_text(encoding="utf-8"))


def test_human_review_asset_matches_confirmed_ten_case_scorecard() -> None:
    payload = _payload()
    reviews = payload["reviews"]
    expected_winners = {
        "TC-KNOWLEDGE-001": "TIE",
        "TC-KNOWLEDGE-002": "TIE",
        "TC-KNOWLEDGE-003": "TIE",
        "TC-KNOWLEDGE-004": "GUARDED",
        "TC-KNOWLEDGE-005": "TIE",
        "TC-KNOWLEDGE-006": "OFF",
        "TC-KNOWLEDGE-007": "TIE",
        "TC-KNOWLEDGE-008": "TIE",
        "TC-KNOWLEDGE-009": "GUARDED",
        "TC-KNOWLEDGE-010": "GUARDED",
    }

    assert len(reviews) == 10
    assert {row["case_id"]: row["winner"] for row in reviews} == expected_winners
    assert Counter(row["winner"] for row in reviews) == Counter({"TIE": 6, "GUARDED": 3, "OFF": 1})
    assert all(row["status"] == "passed" for row in reviews)
    assert all(row["reviewer"] == "钱诺成" for row in reviews)
    assert payload["summary"] == {
        "total_cases": 10,
        "guarded_wins": 3,
        "off_wins": 1,
        "ties": 6,
    }


def test_human_review_asset_contains_only_desensitized_review_fields() -> None:
    allowed_fields = {
        "case_id",
        "status",
        "winner",
        "reviewer",
        "reviewed_at",
        "comments",
        "reason",
        "action_items",
    }
    for row in _payload()["reviews"]:
        assert set(row) == allowed_fields
        assert row["reason"]
        assert row["action_items"] == []
