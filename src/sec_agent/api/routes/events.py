from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from sec_agent.api.deps import get_orchestrator
from sec_agent.domain.models import (
    ApprovalDecision,
    EventContext,
    EventListItem,
    EventStatusUpdate,
    StartRunRequest,
    TimelineEntry,
)
from sec_agent.services.orchestrator import Orchestrator

router = APIRouter(tags=["events"])


@router.post(
    "/runs",
    response_model=EventContext,
    operation_id="start_event_run",
    summary="启动安全事件处理主流程",
)
def start_run(request: StartRunRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> EventContext:
    return orchestrator.start(request)


@router.get(
    "/events",
    response_model=list[EventListItem],
    operation_id="list_events",
    summary="查询安全事件列表",
)
def list_events(orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[EventListItem]:
    items: list[EventListItem] = []
    for ctx in orchestrator.list_events():
        items.append(
            EventListItem(
                event_id=ctx.event_id,
                run_id=ctx.run_id,
                trace_id=ctx.trace_id,
                status=ctx.status,
                source=ctx.source,
                sample_id=ctx.request.sample_id if ctx.request else None,
                xdr_event_id=ctx.request.xdr_event_id if ctx.request else None,
                requested_source=ctx.requested_source,
                effective_source=ctx.effective_source,
                fallback_source=ctx.fallback_source,
                summary=ctx.event_summary.summary if ctx.event_summary else None,
            )
        )
    return items


@router.get(
    "/events/{event_id}",
    response_model=EventContext,
    operation_id="get_event",
    summary="查询安全事件详情",
)
def get_event(event_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> EventContext:
    ctx = orchestrator.get_event(event_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="event not found")
    return ctx


@router.get(
    "/events/{event_id}/timeline",
    response_model=list[TimelineEntry],
    operation_id="get_event_timeline",
    summary="查询安全事件状态时间线",
)
def get_timeline(event_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[TimelineEntry]:
    ctx = orchestrator.get_event(event_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="event not found")
    return ctx.timeline


@router.patch(
    "/events/{event_id}",
    response_model=EventContext,
    operation_id="update_event_status",
    summary="更新安全事件状态",
)
def update_event_status(
    event_id: str,
    update: EventStatusUpdate,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> EventContext:
    try:
        return orchestrator.update_event_status(event_id, update)
    except KeyError:
        raise HTTPException(status_code=404, detail="event not found") from None


@router.delete(
    "/events/{event_id}",
    status_code=204,
    operation_id="delete_event",
    summary="删除安全事件",
)
def delete_event(event_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> Response:
    if not orchestrator.delete_event(event_id):
        raise HTTPException(status_code=404, detail="event not found")
    return Response(status_code=204)


@router.post(
    "/events/{event_id}/approval",
    response_model=EventContext,
    operation_id="submit_event_approval",
    summary="提交安全事件处置审批结果",
)
def submit_approval(
    event_id: str,
    decision: ApprovalDecision,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> EventContext:
    try:
        return orchestrator.approve(event_id, decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="event not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
