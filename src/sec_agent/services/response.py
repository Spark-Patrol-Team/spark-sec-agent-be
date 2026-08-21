from __future__ import annotations

from sec_agent.domain.models import (
    ApprovalStatus,
    BusinessStatus,
    ExecutionMode,
    ExecutionResult,
    InvestigationReport,
    ResponsePlan,
    ToolRequest,
    ToolCallStatus,
    ToolRiskLevel,
    VerificationResult,
    VerificationStatus,
)
from sec_agent.platforms.base import PlatformAdapter


class ResponseDecisionService:
    def build_plan(self, report: InvestigationReport) -> ResponsePlan | None:
        if report.needs_human or not report.recommended_actions:
            return None

        target = report.affected_objects[0] if report.affected_objects else "unknown-target"
        return ResponsePlan(
            action="stateful_mock_containment",
            target=target,
            reason="基于调查报告建议执行有状态 Mock 处置，真实高风险动作等待平台权限确认",
            risk_level=ToolRiskLevel.HIGH,
            approval_required=True,
            rollback_available=True,
        )


class ResponseExecutionService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def execute(self, trace_id: str, event_id: str, plan: ResponsePlan, idempotency_key: str) -> ExecutionResult:
        request = ToolRequest(
            trace_id=trace_id,
            tool_name="stateful_response_mock",
            action_name=plan.action,
            params={"event_id": event_id, "target": plan.target},
            reason=plan.reason,
            dry_run=False,
            idempotency_key=idempotency_key,
            risk_level=plan.risk_level,
            approval_status=ApprovalStatus.APPROVED,
        )
        result = self._platform.run_tool(request)
        return ExecutionResult(
            executed=result.status == ToolCallStatus.SUCCESS,
            mode=ExecutionMode.MOCK,
            platform_status=result.status,
            error=result.error_type,
            retry_count=0,
            idempotency_key=idempotency_key,
        )


class ResponseVerificationService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def verify(self, trace_id: str, event_id: str, execution: ExecutionResult) -> VerificationResult:
        status = self._platform.query_action_status(execution.idempotency_key)
        final_status = BusinessStatus.COMPLETED if status == "executed" else BusinessStatus.HUMAN_REQUIRED
        verification_status = VerificationStatus.EFFECTIVE if status == "executed" else VerificationStatus.UNKNOWN
        return VerificationResult(
            status=verification_status,
            method="查询有状态 Mock 处置记录",
            evidence_refs=[f"fixed://actions/{execution.idempotency_key}"] if status == "executed" else [],
            adjustment_suggestion=None if status == "executed" else "无法确认处置生效，需要人工接管",
            final_status=final_status,
        )
