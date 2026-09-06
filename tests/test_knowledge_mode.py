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