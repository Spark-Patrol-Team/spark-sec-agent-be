from __future__ import annotations

from uuid import uuid4

from sec_agent.domain.models import (
    ApprovalDecision,
    BusinessStatus,
    ErrorRecord,
    EventContext,
    ResponseResult,
    StartRunRequest,
    TimelineEntry,
)
from sec_agent.domain.state_machine import StateMachine
from sec_agent.platforms.base import PlatformAdapter
from sec_agent.services.correlation import AlertCorrelationService
from sec_agent.services.ingest import AlertIngestService
from sec_agent.services.investigation import DeepInvestigationAgent
from sec_agent.services.response import (
    ResponseDecisionService,
    ResponseExecutionService,
    ResponseVerificationService,
)
from sec_agent.services.triage import RiskTriageService
from sec_agent.repositories.base import EventRepository


class Orchestrator:
    def __init__(self, platform: PlatformAdapter, store: EventRepository) -> None:
        self._store = store
        self._state = StateMachine()
        self._ingest = AlertIngestService(platform)
        self._correlation = AlertCorrelationService()
        self._triage = RiskTriageService()
        self._investigation = DeepInvestigationAgent(platform)
        self._decision = ResponseDecisionService()
        self._execution = ResponseExecutionService(platform)
        self._verification = ResponseVerificationService(platform)

    def start(self, request: StartRunRequest) -> EventContext:
        trace_id = f"trace-{uuid4()}"
        run_id = f"run-{uuid4()}"

        try:
            alerts = self._ingest.ingest(request.source, request.sample_id, request.xdr_event_id)
        except Exception as exc:
            ctx = EventContext(
                trace_id=trace_id,
                run_id=run_id,
                event_id=f"evt-{uuid4()}",
                status=BusinessStatus.FAILED,
                source=request.source,
                timeline=[TimelineEntry(status=BusinessStatus.FAILED, message="告警接入失败")],
                errors=[ErrorRecord(stage="ingest", message=str(exc), recoverable=True)],
            )
            return self._store.save(ctx)

        event_id = f"evt-{uuid4()}"
        ctx = EventContext(
            trace_id=trace_id,
            run_id=run_id,
            event_id=event_id,
            status=BusinessStatus.RECEIVED,
            source=request.source,
            alert_refs=[alert.alert_id for alert in alerts],
            timeline=[TimelineEntry(status=BusinessStatus.RECEIVED, message="已接收告警输入")],
        )
        self._store.save(ctx)

        try:
            ctx = self._state.move(ctx, BusinessStatus.CORRELATING, "开始告警关联")
            event = self._correlation.correlate(alerts)
            event.event_id = ctx.event_id
            ctx.event_summary = event

            ctx = self._state.move(ctx, BusinessStatus.TRIAGED, "完成告警关联，开始风险研判")
            ctx.triage = self._triage.triage(event, alerts)
            if not ctx.triage.should_investigate:
                ctx = self._state.move(ctx, BusinessStatus.COMPLETED, "低风险或明确误报，分诊结束")
                return self._store.save(ctx)

            ctx = self._state.move(ctx, BusinessStatus.INVESTIGATING, "进入深度调查")
            ctx.investigation = self._investigation.investigate(ctx.trace_id, event, ctx.triage)
            if ctx.investigation.needs_human:
                ctx = self._state.move(ctx, BusinessStatus.HUMAN_REQUIRED, "调查证据不足，需要人工接管")
                return self._store.save(ctx)

            ctx = self._state.move(ctx, BusinessStatus.DECISION_READY, "已形成处置方案")
            plan = self._decision.build_plan(ctx.investigation)
            ctx.response = ResponseResult(plan=plan)
            if plan is None:
                ctx = self._state.move(ctx, BusinessStatus.HUMAN_REQUIRED, "未形成可自动执行的处置方案")
                return self._store.save(ctx)

            if plan.approval_required:
                ctx = self._state.move(ctx, BusinessStatus.APPROVAL_REQUIRED, "高风险动作等待人工审批")
                return self._store.save(ctx)

            return self._execute_and_verify(ctx, idempotency_key=f"{ctx.event_id}:auto-execute")
        except Exception as exc:
            ctx.errors.append(ErrorRecord(stage="orchestrator", message=str(exc), recoverable=False))
            if ctx.status != BusinessStatus.FAILED:
                ctx = self._state.move(ctx, BusinessStatus.FAILED, "主流程异常，无法继续处理")
            return self._store.save(ctx)

    def approve(self, event_id: str, decision: ApprovalDecision) -> EventContext:
        ctx = self._must_get(event_id)
        if ctx.status != BusinessStatus.APPROVAL_REQUIRED:
            raise ValueError(f"当前状态不允许审批: {ctx.status}")

        if not self._store.claim_idempotency_key(decision.idempotency_key):
            return ctx

        if not decision.approved:
            ctx = self._state.move(ctx, BusinessStatus.HUMAN_REQUIRED, "审批拒绝，转人工处理")
            return self._store.save(ctx)

        return self._execute_and_verify(ctx, idempotency_key=decision.idempotency_key)

    def list_events(self) -> list[EventContext]:
        return self._store.list()

    def get_event(self, event_id: str) -> EventContext | None:
        return self._store.get(event_id)

    def _execute_and_verify(self, ctx: EventContext, idempotency_key: str) -> EventContext:
        if ctx.response is None or ctx.response.plan is None:
            raise ValueError("缺少处置方案，无法执行")

        ctx = self._state.move(ctx, BusinessStatus.EXECUTING, "开始执行处置动作")
        execution = self._execution.execute(ctx.trace_id, ctx.event_id, ctx.response.plan, idempotency_key)
        ctx.response.execution = execution
        if not execution.executed:
            ctx = self._state.move(ctx, BusinessStatus.FAILED, "处置执行失败")
            return self._store.save(ctx)

        ctx = self._state.move(ctx, BusinessStatus.VERIFYING, "开始执行后独立验证")
        verification = self._verification.verify(ctx.trace_id, ctx.event_id, execution)
        ctx.response.verification = verification
        ctx = self._state.move(ctx, verification.final_status, "处置验证完成")
        return self._store.save(ctx)

    def _must_get(self, event_id: str) -> EventContext:
        ctx = self._store.get(event_id)
        if ctx is None:
            raise KeyError(event_id)
        return ctx
