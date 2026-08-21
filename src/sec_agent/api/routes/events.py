from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from sec_agent.api.deps import get_orchestrator
from sec_agent.domain.models import ApprovalDecision, EventListItem, StartRunRequest
from sec_agent.services.orchestrator import Orchestrator

router = APIRouter(tags=["events"])


@router.post("/runs")
def start_run(request: StartRunRequest, orchestrator: Orchestrator = Depends(get_orchestrator)):
    return orchestrator.start(request)


@router.get("/events", response_model=list[EventListItem])
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
                summary=ctx.event_summary.summary if ctx.event_summary else None,
            )
        )
    return items


@router.get("/events/{event_id}")
def get_event(event_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)):
    ctx = orchestrator.get_event(event_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="event not found")
    return ctx


@router.get("/events/{event_id}/timeline")
def get_timeline(event_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)):
    ctx = orchestrator.get_event(event_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="event not found")
    return ctx.timeline


@router.post("/events/{event_id}/approval")
def submit_approval(
    event_id: str,
    decision: ApprovalDecision,
    orchestrator: Orchestrator = Depends(get_orchestrator),
):
    try:
        return orchestrator.approve(event_id, decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="event not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

