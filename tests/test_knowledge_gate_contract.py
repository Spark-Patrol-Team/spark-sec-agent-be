from sec_agent.deep_agent.tools.knowledge import KnowledgeQueryTool


def test_in_scope_returns_knowledge():
    tool = KnowledgeQueryTool(gate_decision="in_scope")

    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "success"
    assert result.data["knowledge_id"] == "WSK-013"
    assert result.data["required_evidence"]


def test_weak_signal_blocks_confirmatory_knowledge():
    tool = KnowledgeQueryTool(gate_decision="weak_signal")

    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "partial"
    assert result.data["gate_decision"] == "weak_signal"
    assert result.data["knowledge_returned"] is False
    assert result.data["restriction"] == "confirmatory_knowledge_blocked"


def test_out_of_scope_returns_scope_mismatch():
    tool = KnowledgeQueryTool(gate_decision="out_of_scope")

    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "failed"
    assert result.error == "knowledge_scope_mismatch"
    assert result.data["gate_decision"] == "out_of_scope"
    assert result.data["knowledge_returned"] is False

def test_not_found_is_distinct():
    tool = KnowledgeQueryTool(gate_decision="in_scope")

    result = tool.call({"keyword": "数据库性能调优"})

    assert result.status == "failed"
    assert result.error == "knowledge_not_found"
    assert result.retryable is False
    assert result.data["knowledge_returned"] is False


def test_timeout_is_distinct(monkeypatch):
    from sec_agent.deep_agent.tools import knowledge

    def raise_timeout(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(
        knowledge,
        "match_knowledge_card",
        raise_timeout,
    )

    tool = KnowledgeQueryTool(gate_decision="in_scope")
    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "failed"
    assert result.error == "knowledge_timeout"
    assert result.retryable is True
    assert result.data["knowledge_returned"] is False


def test_internal_error_is_distinct(monkeypatch):
    from sec_agent.deep_agent.tools import knowledge

    def raise_error(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        knowledge,
        "match_knowledge_card",
        raise_error,
    )

    tool = KnowledgeQueryTool(gate_decision="in_scope")
    result = tool.call({"keyword": "WebShell 植入方式"})

    assert result.status == "failed"
    assert result.error == "knowledge_internal_error"
    assert result.retryable is False
    assert result.data["knowledge_returned"] is False
    assert result.data["error_type"] == "RuntimeError"