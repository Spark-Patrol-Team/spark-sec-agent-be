from __future__ import annotations

from fastapi import APIRouter, Depends

from sec_agent.api.deps import get_orchestrator
from sec_agent.api.schemas import MetricsResponse
from sec_agent.services.orchestrator import Orchestrator

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    operation_id="get_metrics",
    summary="查询基础处理指标",
)
def get_metrics(orchestrator: Orchestrator = Depends(get_orchestrator)) -> MetricsResponse:
    events = orchestrator.list_events()
    total = len(events)
    completed = sum(1 for ctx in events if ctx.status == "COMPLETED")
    human_required = sum(1 for ctx in events if ctx.status == "HUMAN_REQUIRED")
    failed = sum(1 for ctx in events if ctx.status == "FAILED")
    return {
        "total_events": total,
        "completed_events": completed,
        "human_required_events": human_required,
        "failed_events": failed,
        "note": "无可靠标签时不统计准确率、召回率等指标",
    }
