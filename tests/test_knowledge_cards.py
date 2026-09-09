from pathlib import Path

from sec_agent.deep_agent.tools.knowledge import parse_knowledge_cards
import pytest

KNOWLEDGE_PATH = Path(
    "src/sec_agent/deep_agent/knowledge/webshell-knowledge.md"
)


def test_parse_all_knowledge_cards():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    assert len(cards) == 15


def test_knowledge_ids_are_unique():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    ids = [card.knowledge_id for card in cards]

    assert len(ids) == len(set(ids))


def test_all_knowledge_cards_have_required_fields():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    for card in cards:
        assert card.knowledge_id
        assert card.topic
        assert card.applicability
        assert card.required_evidence
        assert card.investigation_steps
        assert card.false_positives
        assert card.prohibited_inference
        assert card.source_urls
        assert card.source_levels
        assert card.related_cases




def test_missing_knowledge_id_fails_explicitly():
    bad_card = """
- 主题：缺失ID测试
- 适用条件：
  - test
- 必要证据：
  - test
- 调查步骤：
  - test
- 常见误报：
  - test
- 禁止推断：
  - test
- 来源URL：
  - test
- 来源等级：
  - test
- 关联案例：
  - test
"""

    from sec_agent.deep_agent.tools.knowledge import parse_knowledge_card

    with pytest.raises(ValueError, match="missing knowledge_id"):
        parse_knowledge_card(bad_card)


def test_duplicate_knowledge_id_fails_explicitly():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")

    first_card = text.split("## 知识ID：WSK-002")[0]
    duplicated = first_card + "\n" + first_card

    with pytest.raises(ValueError, match="duplicate knowledge_id: WSK-001"):
        parse_knowledge_cards(duplicated)

from sec_agent.deep_agent.tools.knowledge import match_knowledge_card


def test_query_matches_correct_knowledge_card():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    card = match_knowledge_card(cards, "WebShell 植入方式")

    assert card is not None
    assert card.knowledge_id == "WSK-013"


def test_empty_query_returns_none():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    assert match_knowledge_card(cards, "") is None


def test_unknown_subject_returns_none():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)

    assert match_knowledge_card(cards, "数据库备份性能调优") is None

from sec_agent.deep_agent.tools.knowledge import KnowledgeQueryTool


def test_knowledge_query_returns_structured_card():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)
    tool = KnowledgeQueryTool(cards)

    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "success"
    assert result.data["knowledge_id"] == "WSK-013"
    assert result.data["topic"] == "WebShell 植入方式"
    assert result.data["applicability"]
    assert result.data["required_evidence"]
    assert result.data["false_positives"]
    assert result.data["prohibited_inference"]
    assert result.data["source_citations"]["urls"]
    assert result.data["source_citations"]["levels"]


def test_knowledge_query_empty_keyword_is_clear_failure():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)
    tool = KnowledgeQueryTool(cards)

    result = tool.call({"keyword": ""})

    assert result.status == "failed"
    assert result.error == "empty_knowledge_query"


def test_knowledge_query_unknown_subject_returns_no_unrelated_card():
    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    cards = parse_knowledge_cards(text)
    tool = KnowledgeQueryTool(cards)

    result = tool.call({"keyword": "数据库备份性能调优"})

    assert result.status == "failed"
    assert result.error == "knowledge_not_found"