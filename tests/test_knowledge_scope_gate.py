from sec_agent.deep_agent.tools.knowledge import (
    KnowledgeEntry,
    KnowledgeQueryTool,
)


def test_out_of_scope_never_returns_webshell_content():
    entries = [
        KnowledgeEntry(
            name="攻击原理",
            keywords=["WebShell攻击原理"],
            content="这是 WebShell 正文，不应该在域外事件中返回。",
            evidence_refs=["test-ref"],
        )
    ]

    tool = KnowledgeQueryTool(
        entries=entries,
        event_context={"overall_strength": "OUT_OF_SCOPE"},
    )

    result = tool.call({"keyword": "WebShell攻击原理"})

    assert result.status == "failed"
    assert result.error == "knowledge_scope_mismatch"
    assert result.data["gate"] == "out_of_scope"
    assert result.data["knowledge_returned"] is False
    assert "这是 WebShell 正文" not in result.summary

def test_weak_signal_returns_restricted_result():
    entries = [
        KnowledgeEntry(
            name="攻击原理",
            keywords=["WebShell攻击原理"],
            content="这是确认性 WebShell 正文，弱信号阶段不应该返回。",
            evidence_refs=["test-ref"],
        )
    ]

    tool = KnowledgeQueryTool(
        entries=entries,
        event_context={"overall_strength": "IN_SCOPE_WEAK"},
    )

    result = tool.call({"keyword": "WebShell攻击原理"})

    assert result.status == "partial"
    assert result.data["gate"] == "weak_signal"
    assert result.data["knowledge_returned"] is False
    assert "这是确认性 WebShell 正文" not in result.summary

def test_in_scope_returns_matching_knowledge():
    entries = [
        KnowledgeEntry(
            name="攻击原理",
            keywords=["WebShell攻击原理"],
            content="这是允许返回的 WebShell 知识正文。",
            evidence_refs=["test-ref"],
        )
    ]

    tool = KnowledgeQueryTool(
        entries=entries,
        event_context={"overall_strength": "IN_SCOPE_CONFIRMED"},
    )

    result = tool.call({"keyword": "WebShell攻击原理"})

    assert result.status == "success"
    assert "这是允许返回的 WebShell 知识正文" in result.summary
    assert result.data["entry"] == "攻击原理"