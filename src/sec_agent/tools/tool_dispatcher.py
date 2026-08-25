from __future__ import annotations

from collections.abc import Callable, Mapping

from sec_agent.domain.models import (
    ToolRequest,
    ToolResult,
)
from sec_agent.tools.base import ToolDispatcher
from sec_agent.tools.stateful_mock_tool import (
    ResponseLedger,
    build_response_verify_handler,
    build_stateful_response_handler,
    handle_stateful_mock,
)
from sec_agent.tools.xdr_query_tool import build_evidence_lookup_handler, handle_xdr_query


ToolHandler = Callable[[ToolRequest], ToolResult]


def build_platform_tool_dispatcher(
    *,
    evidence_resolver: Callable[[ToolRequest], list[str]],
    ledger: ResponseLedger,
    raw_result_prefix: str,
    action_ref_prefix: str,
    source_label: str,
    extra_handlers: Mapping[str, ToolHandler] | None = None,
) -> ToolDispatcher:
    handlers: dict[str, ToolHandler] = {
        "evidence_lookup": build_evidence_lookup_handler(
            evidence_resolver=evidence_resolver,
            raw_result_prefix=raw_result_prefix,
            source_label=source_label,
        ),
        "stateful_response_mock": build_stateful_response_handler(
            ledger=ledger,
            raw_result_prefix=raw_result_prefix,
            action_ref_prefix=action_ref_prefix,
            source_label=source_label,
        ),
        "response_verify": build_response_verify_handler(
            ledger=ledger,
            raw_result_prefix=raw_result_prefix,
            source_label=source_label,
        ),
        "xdr_log_query": handle_xdr_query,
        "stateful_mock": handle_stateful_mock,
    }
    if extra_handlers:
        handlers.update(extra_handlers)
    return ToolDispatcher(handlers)
