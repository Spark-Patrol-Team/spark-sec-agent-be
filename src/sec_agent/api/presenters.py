from __future__ import annotations

from datetime import datetime

from sec_agent.domain.models import (
    BusinessStatus,
    EventContext,
    EventDetailView,
    EventErrorView,
    EventInvestigationView,
    EventListItem,
    EventOverviewView,
    EventResponseView,
    EventSourceView,
    EventTimelineView,
    Priority,
    TruthVerdict,
)


_STATUS_LABELS: dict[BusinessStatus, str] = {
    BusinessStatus.RECEIVED: "已接收",
    BusinessStatus.CORRELATING: "关联中",
    BusinessStatus.TRIAGED: "已研判",
    BusinessStatus.INVESTIGATING: "调查中",
    BusinessStatus.DECISION_READY: "待决策",
    BusinessStatus.APPROVAL_REQUIRED: "待审批",
    BusinessStatus.EXECUTING: "执行中",
    BusinessStatus.VERIFYING: "验证中",
    BusinessStatus.COMPLETED: "已完成",
    BusinessStatus.HUMAN_REQUIRED: "需人工处理",
    BusinessStatus.FAILED: "失败",
}

_EVENT_TYPE_LABELS: dict[str, str] = {
    "sql_injection": "SQL 注入",
    "webshell": "WebShell",
    "lateral_movement": "横向移动",
    "unauthorized_access": "未授权访问",
    "other": "安全告警",
}


def to_event_list_item(ctx: EventContext) -> EventListItem:
    created_at, updated_at = _timeline_bounds(ctx)
    return EventListItem(
        event_id=ctx.event_id,
        run_id=ctx.run_id,
        trace_id=ctx.trace_id,
        status=ctx.status,
        status_label=_status_label(ctx.status),
        source=ctx.source,
        sample_id=ctx.request.sample_id if ctx.request else None,
        xdr_event_id=ctx.request.xdr_event_id if ctx.request else None,
        requested_source=ctx.requested_source,
        effective_source=ctx.effective_source,
        fallback_source=ctx.fallback_source,
        alert_count=_alert_count(ctx),
        risk_score=ctx.triage.risk_score if ctx.triage else None,
        priority=ctx.triage.priority if ctx.triage else None,
        verdict=ctx.triage.verdict if ctx.triage else None,
        created_at=created_at,
        updated_at=updated_at,
        summary=ctx.event_summary.summary if ctx.event_summary else _first_error_message(ctx),
    )


def to_event_detail_view(ctx: EventContext) -> EventDetailView:
    created_at, updated_at = _timeline_bounds(ctx)
    return EventDetailView(
        schema_version=ctx.schema_version,
        event_id=ctx.event_id,
        run_id=ctx.run_id,
        trace_id=ctx.trace_id,
        status=ctx.status,
        status_label=_status_label(ctx.status),
        source=EventSourceView(
            requested=ctx.requested_source,
            effective=ctx.effective_source,
            fallback=ctx.fallback_source,
            sample_id=ctx.request.sample_id if ctx.request else None,
            xdr_event_id=ctx.request.xdr_event_id if ctx.request else None,
        ),
        overview=_overview(ctx),
        timeline=[
            EventTimelineView(
                at=item.at,
                status=item.status,
                status_label=_status_label(item.status),
                message=item.message,
                elapsed_ms=item.elapsed_ms,
            )
            for item in ctx.timeline
        ],
        errors=[
            EventErrorView(
                at=item.at,
                stage=item.stage,
                message=item.message,
                recoverable=item.recoverable,
            )
            for item in ctx.errors
        ],
        investigation=_investigation(ctx),
        response=_response(ctx),
        created_at=created_at,
        updated_at=updated_at,
    )


def _overview(ctx: EventContext) -> EventOverviewView:
    entities = ctx.event_summary.entities if ctx.event_summary else {}
    return EventOverviewView(
        title=_title(ctx),
        summary=ctx.event_summary.summary if ctx.event_summary else _first_error_message(ctx),
        alert_count=_alert_count(ctx),
        risk_score=ctx.triage.risk_score if ctx.triage else None,
        priority=ctx.triage.priority if ctx.triage else None,
        verdict=ctx.triage.verdict if ctx.triage else None,
        confidence=ctx.triage.confidence if ctx.triage else None,
        needs_human=ctx.status == BusinessStatus.HUMAN_REQUIRED
        or bool(ctx.investigation and ctx.investigation.needs_human),
        affected_assets=_unique(entities.get("assets", [])),
        source_ips=_unique(entities.get("src_ips", [])),
        destination_ips=_unique(entities.get("dst_ips", [])),
    )


def _investigation(ctx: EventContext) -> EventInvestigationView | None:
    if ctx.investigation is None:
        return None
    return EventInvestigationView(
        conclusion=ctx.investigation.conclusion,
        final_confidence=ctx.investigation.final_confidence,
        summary=ctx.investigation.summary,
        affected_objects=_unique(ctx.investigation.affected_objects),
        unresolved_questions=_unique(ctx.investigation.unresolved_questions),
        recommended_actions=_unique(ctx.investigation.recommended_actions),
        key_evidence_refs=_clean_evidence_refs(ctx.investigation.key_evidence_refs),
        tool_result_count=len(ctx.investigation.tool_results),
    )


def _response(ctx: EventContext) -> EventResponseView | None:
    if ctx.response is None:
        return None
    plan = ctx.response.plan
    execution = ctx.response.execution
    verification = ctx.response.verification
    return EventResponseView(
        action=plan.action if plan else None,
        target=plan.target if plan else None,
        risk_level=plan.risk_level if plan else None,
        approval_required=plan.approval_required if plan else None,
        execution_status=execution.status if execution else None,
        verification_status=verification.status if verification else None,
        final_status=verification.final_status if verification else None,
    )


def _title(ctx: EventContext) -> str:
    event_type = _event_type(ctx)
    if ctx.status == BusinessStatus.FAILED:
        return f"{event_type}处理失败"
    if ctx.status == BusinessStatus.HUMAN_REQUIRED:
        return f"{event_type}需人工处理"
    return f"{event_type}安全事件"


def _event_type(ctx: EventContext) -> str:
    text_parts = []
    if ctx.event_summary:
        text_parts.extend([ctx.event_summary.summary, ctx.event_summary.correlation_reason])
    for text in text_parts:
        for key, label in _EVENT_TYPE_LABELS.items():
            if key in text:
                return label
    return "安全告警"


def _alert_count(ctx: EventContext) -> int:
    if ctx.event_summary is not None:
        return ctx.event_summary.alert_count_before
    return len(ctx.alert_refs)


def _status_label(status: BusinessStatus) -> str:
    return _STATUS_LABELS.get(status, status.value)


def _timeline_bounds(ctx: EventContext) -> tuple[datetime | None, datetime | None]:
    if not ctx.timeline:
        return None, None
    return ctx.timeline[0].at, ctx.timeline[-1].at


def _first_error_message(ctx: EventContext) -> str | None:
    if not ctx.errors:
        return None
    return ctx.errors[0].message


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _clean_evidence_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = value.strip()
        if not text or len(text) > 200:
            continue
        if any(char in text for char in "{}[]'\" \n\r\t"):
            continue
        result.append(text)
        if len(result) >= 20:
            break
    return _unique(result)
