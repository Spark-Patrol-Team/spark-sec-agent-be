from __future__ import annotations

from uuid import uuid4

from sec_agent.domain.models import (
    ApprovalDecision,
    AlertRecord,
    BusinessStatus,
    ErrorRecord,
    EventContext,
    EventStatusUpdate,
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
    def __init__(
        self,
        platform: PlatformAdapter,
        store: EventRepository,
        investigation_backend: str = "auto",
        platform_backend: str | None = None,
    ) -> None:
        self._store = store
        self._state = StateMachine()
        self._ingest = AlertIngestService(platform, platform_backend=platform_backend)
        self._correlation = AlertCorrelationService()
        self._triage = RiskTriageService()
        self._investigation = DeepInvestigationAgent(platform, backend=investigation_backend)
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
                request=request,
                requested_source=request.source,
                timeline=[TimelineEntry(status=BusinessStatus.FAILED, message="告警接入失败")],
                errors=[ErrorRecord(stage="ingest", message=str(exc), recoverable=True)],
            )
            return self._store.save(ctx)

        fallback_reason = self._platform_fallback_reason(alerts)
        fallback_source = self._fallback_source(alerts)
        received_message = "已接收告警输入"
        initial_errors: list[ErrorRecord] = []
        if fallback_reason:
            received_message = "已接收告警输入；真实平台失败，已降级到固定样例"
            initial_errors.append(
                ErrorRecord(
                    stage="ingest",
                    message=f"真实平台降级到固定样例: {fallback_reason}",
                    recoverable=True,
                )
            )

        event_id = f"evt-{uuid4()}"
        ctx = EventContext(
            trace_id=trace_id,
            run_id=run_id,
            event_id=event_id,
            status=BusinessStatus.RECEIVED,
            source=request.source,
            request=request,
            requested_source=request.source,
            effective_source=self._effective_source(alerts),
            fallback_source=fallback_source,
            alert_refs=[alert.alert_id for alert in alerts],
            timeline=[TimelineEntry(status=BusinessStatus.RECEIVED, message=received_message)],
            errors=initial_errors,
        )
        self._store.save(ctx)

        try:
            ctx = self._move(ctx, BusinessStatus.CORRELATING, "开始告警关联")
            event = self._correlation.correlate(alerts)
            event.event_id = ctx.event_id
            ctx.event_summary = event
            self._store.save(ctx)

            ctx.triage = self._triage.triage(event, alerts)
            ctx = self._move(ctx, BusinessStatus.TRIAGED, "完成风险研判")
            if not ctx.triage.should_investigate:
                return self._move(ctx, BusinessStatus.COMPLETED, "低风险或明确误报，分诊结束")

            ctx = self._move(ctx, BusinessStatus.INVESTIGATING, "进入深度调查")
            ctx.investigation = self._investigation.investigate(ctx.trace_id, event, ctx.triage, run_id=ctx.run_id)
            self._store.save(ctx)
            if ctx.investigation.needs_human:
                return self._move(ctx, BusinessStatus.HUMAN_REQUIRED, "调查证据不足，需要人工接管")

            plan = self._decision.build_plan(ctx.investigation, ctx.triage)
            if plan is None:
                return self._move(ctx, BusinessStatus.HUMAN_REQUIRED, "未形成可自动执行的处置方案")

            ctx.response = ResponseResult(plan=plan)
            self._store.save(ctx)
            ctx = self._move(ctx, BusinessStatus.DECISION_READY, "已形成处置方案")

            if plan.approval_required:
                return self._move(ctx, BusinessStatus.APPROVAL_REQUIRED, "高风险动作等待人工审批")

            return self._execute_and_verify(ctx, idempotency_key=f"{ctx.event_id}:auto-execute")
        except Exception as exc:
            ctx.errors.append(ErrorRecord(stage="orchestrator", message=str(exc), recoverable=False))
            if ctx.status != BusinessStatus.FAILED:
                ctx = self._state.move(ctx, BusinessStatus.FAILED, "主流程异常，无法继续处理")
            return self._store.save(ctx)

    def approve(self, event_id: str, decision: ApprovalDecision) -> EventContext:
        ctx = self._must_get(event_id)
        if self._store.has_idempotency_key(decision.idempotency_key):
            return ctx

        if ctx.status != BusinessStatus.APPROVAL_REQUIRED:
            raise ValueError(f"当前状态不允许审批: {ctx.status}")

        if not self._store.claim_idempotency_key(decision.idempotency_key):
            return ctx

        if not decision.approved:
            return self._move(ctx, BusinessStatus.HUMAN_REQUIRED, "审批拒绝，转人工处理")

        return self._execute_and_verify(ctx, idempotency_key=decision.idempotency_key, idempotency_claimed=True)

    def list_events(self) -> list[EventContext]:
        return self._store.list()

    def get_event(self, event_id: str) -> EventContext | None:
        return self._store.get(event_id)

    def update_event_status(self, event_id: str, update: EventStatusUpdate) -> EventContext:
        ctx = self._must_get(event_id)
        ctx.status = update.status
        ctx.timeline.append(
            TimelineEntry(
                status=update.status,
                message=update.message or "手动更新事件状态",
            )
        )
        return self._store.save(ctx)

    def delete_event(self, event_id: str) -> bool:
        return self._store.delete(event_id)

    def _execute_and_verify(
        self,
        ctx: EventContext,
        idempotency_key: str,
        idempotency_claimed: bool = False,
    ) -> EventContext:
        if ctx.response is None or ctx.response.plan is None:
            raise ValueError("缺少处置方案，无法执行")
        if not idempotency_claimed and not self._store.claim_idempotency_key(idempotency_key):
            return ctx

        ctx = self._move(ctx, BusinessStatus.EXECUTING, "开始执行处置动作")
        execution = self._execution.execute(ctx.trace_id, ctx.event_id, ctx.response.plan, idempotency_key)
        ctx.response.execution = execution
        self._store.save(ctx)
        if not execution.executed:
            return self._move(ctx, BusinessStatus.FAILED, "处置执行失败")

        ctx = self._move(ctx, BusinessStatus.VERIFYING, "开始执行后独立验证")
        verification = self._verification.verify(ctx.trace_id, ctx.event_id, execution)
        ctx.response.verification = verification
        self._store.save(ctx)
        return self._move(ctx, verification.final_status, "处置验证完成")

    def _must_get(self, event_id: str) -> EventContext:
        ctx = self._store.get(event_id)
        if ctx is None:
            raise KeyError(event_id)
        return ctx

    def _move(self, ctx: EventContext, next_status: BusinessStatus, message: str) -> EventContext:
        return self._store.save(self._state.move(ctx, next_status, message))

    @staticmethod
    def _platform_fallback_reason(alerts: list[AlertRecord]) -> str | None:
        for alert in alerts:
            value = alert.scenario_fields.get("platform_fallback_reason")
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _effective_source(alerts: list[AlertRecord]) -> str | None:
        for alert in alerts:
            if alert.source:
                return alert.source
        return None

    @staticmethod
    def _fallback_source(alerts: list[AlertRecord]) -> str | None:
        for alert in alerts:
            value = alert.scenario_fields.get("platform_fallback_source")
            if isinstance(value, str) and value:
                return value
        return None
