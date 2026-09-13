import os

from sec_agent.deep_agent.config import Config
from sec_agent.deep_agent.main import build_tools, normalize_event_payload


def test_normalize_event_payload_accepts_flat_case():
    payload = {"event_id": "flat-1", "event_type": "WebShell"}

    assert normalize_event_payload(payload) is payload


def test_normalize_event_payload_unwraps_formal_case():
    event = {"event_id": "wrapped-1", "event_type": "SSH_Brute_Force"}

    assert normalize_event_payload({"case_id": "TC-10", "input_event": event}) is event


def test_normalize_event_payload_rejects_invalid_wrapper():
    try:
        normalize_event_payload({"input_event": "not-an-object"})
    except ValueError as exc:
        assert "input_event" in str(exc)
    else:
        raise AssertionError("非对象input_event必须显式失败")


def test_knowledge_mode_off_does_not_register_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "off")

    config = Config()
    registry = build_tools(config)

    assert "knowledge_query" not in registry.names()


def test_knowledge_mode_guarded_registers_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "guarded")

    config = Config()
    registry = build_tools(config, gate_decision="in_scope")

    assert "knowledge_query" in registry.names()


def test_knowledge_mode_guarded_without_gate_does_not_register_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "guarded")

    config = Config()
    registry = build_tools(config)

    assert "knowledge_query" not in registry.names()


def test_knowledge_mode_guarded_out_of_scope_does_not_register_tool(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MODE", "guarded")

    config = Config()
    registry = build_tools(config, gate_decision="out_of_scope")

    assert "knowledge_query" not in registry.names()


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
