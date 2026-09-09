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