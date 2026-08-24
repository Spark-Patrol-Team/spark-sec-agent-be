from __future__ import annotations

from dataclasses import dataclass

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
    TriageResult,
)
from sec_agent.platforms.base import PlatformAdapter


@dataclass(frozen=True)
class ResponseRiskPolicy:
    critical_min_score: int = 90
    high_min_score: int = 70
    medium_min_score: int = 40


# 暂存于模块内，后续若出现统一配置中心再迁移。
RESPONSE_RISK_POLICY = ResponseRiskPolicy()


class ResponseDecisionService:
    def build_plan(self, report: InvestigationReport, triage: TriageResult) -> ResponsePlan | None:
        if report.needs_human or not report.recommended_actions:
            return None

        target = report.affected_objects[0] if report.affected_objects else "unknown-target"
        risk_level = self._risk_level_from_triage(triage)
        return ResponsePlan(
            action="stateful_mock_containment",
            target=target,
            reason="基于调查报告建议执行有状态 Mock 处置，真实高风险动作等待平台权限确认",
            risk_level=risk_level,
            approval_required=risk_level in {ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL},
            rollback_available=True,
        )

    def _risk_level_from_triage(self, triage: TriageResult) -> ToolRiskLevel:
        if triage.risk_score >= RESPONSE_RISK_POLICY.critical_min_score:
            return ToolRiskLevel.CRITICAL
        if triage.risk_score >= RESPONSE_RISK_POLICY.high_min_score:
            return ToolRiskLevel.HIGH
        if triage.risk_score >= RESPONSE_RISK_POLICY.medium_min_score:
            return ToolRiskLevel.MEDIUM
        return ToolRiskLevel.LOW


class ResponseExecutionService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def execute(self, trace_id: str, event_id: str, plan: ResponsePlan, idempotency_key: str) -> ExecutionResult:
        request = ToolRequest(
            trace_id=trace_id,
            event_id=event_id,
            stage=BusinessStatus.EXECUTING,
            tool_name="stateful_response_mock",
            action_name=plan.action,
            params={"event_id": event_id, "target": plan.target},
            reason=plan.reason,
            dry_run=False,
            idempotency_key=idempotency_key,
            risk_level=plan.risk_level,
            approval_status=ApprovalStatus.APPROVED,
            timeout_seconds=30,
            max_attempts=1,
        )
        result = self._platform.run_tool(request)
        return ExecutionResult(
            executed=result.status == ToolCallStatus.SUCCESS,
            status=result.status,
            mode=ExecutionMode.MOCK,
            platform_status=result.status.value,
            error=result.error_type.value if result.error_type else None,
            retry_count=0,
            idempotency_key=idempotency_key,
        )


class ResponseVerificationService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def verify(self, trace_id: str, event_id: str, execution: ExecutionResult) -> VerificationResult:
        request = ToolRequest(
            trace_id=trace_id,
            event_id=event_id,
            stage=BusinessStatus.VERIFYING,
            tool_name="response_verify",
            action_name="query_action_status",
            params={"event_id": event_id, "idempotency_key": execution.idempotency_key},
            reason="独立验证处置动作是否生效",
            dry_run=True,
            idempotency_key=execution.idempotency_key,
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            timeout_seconds=30,
            max_attempts=1,
        )
        result = self._platform.run_tool(request)
        action_status = str(
            result.output_preview.get("action_status") or self._platform.query_action_status(execution.idempotency_key)
        )
        if action_status == "executed":
            final_status = BusinessStatus.COMPLETED
            verification_status = VerificationStatus.EFFECTIVE
            adjustment_suggestion = None
        elif action_status == "failed":
            final_status = BusinessStatus.HUMAN_REQUIRED
            verification_status = VerificationStatus.INEFFECTIVE
            adjustment_suggestion = "处置动作未生效，需要人工接管"
        elif result.status == ToolCallStatus.PARTIAL_SUCCESS:
            final_status = BusinessStatus.HUMAN_REQUIRED
            verification_status = VerificationStatus.UNKNOWN
            adjustment_suggestion = "验证结果仅部分可用，需要人工接管"
        else:
            final_status = BusinessStatus.HUMAN_REQUIRED
            verification_status = VerificationStatus.UNKNOWN
            adjustment_suggestion = "无法确认处置生效，需要人工接管"
        return VerificationResult(
            status=verification_status,
            method="通过平台适配器查询有状态 Mock 处置记录",
            evidence_refs=result.evidence_refs,
            adjustment_suggestion=adjustment_suggestion,
            final_status=final_status,
        )
