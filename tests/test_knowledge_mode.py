import os

from sec_agent.deep_agent.config import Config
from sec_agent.deep_agent.main import build_tools


def test_knowledge_mode_off_does_not_register_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "off")

    config = Config()
    registry = build_tools(config)

    assert "knowledge_query" not in registry.names()


def test_knowledge_mode_guarded_registers_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "guarded")

    config = Config()
    registry = build_tools(config)

    assert "knowledge_query" in registry.names()


def test_knowledge_mode_invalid_value_fails_explicitly(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "legacy")

    try:
        Config()
    except ValueError as exc:
        assert "Invalid KNOWLEDGE_MODE" in str(exc)
        assert "off" in str(exc)
        assert "guarded" in str(exc)
    else:
        raise AssertionError("invalid KNOWLEDGE_MODE must fail explicitly")


def test_knowledge_mode_empty_value_fails_explicitly(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "")

    try:
        Config()
    except ValueError as exc:
        assert "Invalid KNOWLEDGE_MODE" in str(exc)
    else:
        raise AssertionError("empty KNOWLEDGE_MODE must fail explicitly")