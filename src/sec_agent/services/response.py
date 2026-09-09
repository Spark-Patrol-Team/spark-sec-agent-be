from __future__ import annotations

from dataclasses import dataclass

from sec_agent.domain.models import (
    ApprovalStatus,
    BusinessStatus,
    ExecutionMode,
    ExecutionResult,
    InvestigationReport,
    ResponseEvidenceScope,
    ResponsePlan,
    SecurityEvent,
    ToolRequest,
    ToolCallStatus,
    ToolRiskLevel,
    VerificationEvidenceLayer,
    VerificationResult,
    VerificationStatus,
    TriageResult,
    TruthVerdict,
)
from sec_agent.platforms.base import PlatformAdapter


@dataclass(frozen=True)
class ResponseRiskPolicy:
    critical_min_score: int = 90
    high_min_score: int = 70
    medium_min_score: int = 40


# 暂存于模块内，后续若出现统一配置中心再迁移。
RESPONSE_RISK_POLICY = ResponseRiskPolicy()


APPROVAL_RISK_LEVELS = {ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL}

WEBSHELL_SCOPE_MARKERS = (
    "webshell",
    "web shell",
    "shell.jsp",
    "shell.php",
    "shell.aspx",
    "shell.ashx",
    "jsp",
    "php",
    "aspx",
    "w3wp.exe",
    "cmd.exe",
    "process.start",
    "runtime.exec",
    "web 进程",
    "web进程",
    "蚁剑",
    "冰蝎",
    "哥斯拉",
)
WEBSHELL_STRONG_MARKERS = (
    "process.start",
    "runtime.exec",
    "w3wp.exe",
    "cmd.exe",
    "eval(",
    "assert(",
    "命令执行",
    "进程创建",
)
OUT_OF_SCOPE_MARKERS = (
    "ssh",
    "暴力破解",
    "brute force",
    "sql_injection",
    "sql 注入",
    "sqli",
    "lateral_movement",
    "横向移动",
    "unauthorized_access",
    "未授权访问",
    "供应链",
    "wordpress_compromise",
)


@dataclass(frozen=True)
class ResponseBoundaryDecision:
    evidence_scope: ResponseEvidenceScope
    max_allowed_risk_level: ToolRiskLevel
    requires_manual_takeover: bool = False
    requires_continued_investigation: bool = False
    reason: str = ""
    basis: tuple[str, ...] = ()


class ResponseEvidenceScopeResolver:
    """在调查完成后，用确定性规则冻结最终处置证据范围。"""

    def resolve(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None = None,
    ) -> ResponseEvidenceScope:
        # 已有的保守结果不可被调查或知识增强升级；in_scope 仍需经过本次调查重算。
        if triage.response_evidence_scope in {
            ResponseEvidenceScope.OUT_OF_SCOPE,
            ResponseEvidenceScope.WEAK_SIGNAL,
        }:
            return triage.response_evidence_scope

        if triage.verdict != TruthVerdict.MALICIOUS or report.conclusion != TruthVerdict.MALICIOUS:
            return ResponseEvidenceScope.OUT_OF_SCOPE

        if self._has_out_of_scope_signal(report, triage, event):
            return ResponseEvidenceScope.OUT_OF_SCOPE

        if self._has_tool_failure(report) or triage.evidence_gaps or report.unresolved_questions:
            return ResponseEvidenceScope.WEAK_SIGNAL

        # 只有上游原始证据达到最小数量时，知识/LLM 产生的报告文本才有资格参与后续边界校验。
        # 这样 knowledge-derived refs 不能单独把范围升级为 in_scope。
        if len({ref for ref in triage.supporting_evidence_refs if ref}) < 2:
            return ResponseEvidenceScope.WEAK_SIGNAL

        if not self._has_webshell_signal(report, triage, event):
            return ResponseEvidenceScope.WEAK_SIGNAL

        return ResponseEvidenceScope.IN_SCOPE

    @staticmethod
    def _has_tool_failure(report: InvestigationReport) -> bool:
        return any(ResponseEvidenceScopeResolver._step_failed(step) for step in report.steps)

    @staticmethod
    def _step_failed(step) -> bool:
        if step.tool_request is not None and step.tool_result is None:
            return True
        return step.tool_result is not None and step.tool_result.status != ToolCallStatus.SUCCESS

    @staticmethod
    def _event_text(
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> str:
        parts = [
            triage.summary,
            *triage.supporting_evidence_refs,
            *triage.opposing_evidence_refs,
            report.summary,
            *report.key_evidence_refs,
            *report.evidence_relations,
            *report.unresolved_questions,
            *report.recommended_actions,
        ]
        if event is not None:
            parts.extend([event.summary, event.correlation_reason, *event.alert_refs])
        return " ".join(str(part).lower() for part in parts if part)

    def _has_webshell_signal(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> bool:
        text = self._event_text(report, triage, event)
        return any(marker in text for marker in WEBSHELL_SCOPE_MARKERS)

    def _has_out_of_scope_signal(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> bool:
        text = self._event_text(report, triage, event)
        return any(marker in text for marker in OUT_OF_SCOPE_MARKERS)


class ResponseDecisionService:
    def build_plan(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None = None,
    ) -> ResponsePlan | None:
        if report.needs_human or not report.recommended_actions:
            return None

        if not report.affected_objects:
            return None

        boundary = self._boundary_decision(report, triage, event)
        if boundary.requires_manual_takeover or boundary.requires_continued_investigation:
            return None

        target = report.affected_objects[0]
        risk_level = self._risk_level_from_triage(triage)
        if self._risk_order(risk_level) > self._risk_order(boundary.max_allowed_risk_level):
            return None

        return ResponsePlan(
            action="stateful_mock_containment",
            target=target,
            reason=f"基于确认的 WebShell 调查报告建议执行有状态 Mock 处置；{boundary.reason}",
            risk_level=risk_level,
            evidence_scope=boundary.evidence_scope,
            max_allowed_risk_level=boundary.max_allowed_risk_level,
            approval_required=risk_level in APPROVAL_RISK_LEVELS,
            rollback_available=True,
            decision_basis=list(boundary.basis),
        )

    def _risk_level_from_triage(self, triage: TriageResult) -> ToolRiskLevel:
        if triage.risk_score >= RESPONSE_RISK_POLICY.critical_min_score:
            return ToolRiskLevel.CRITICAL
        if triage.risk_score >= RESPONSE_RISK_POLICY.high_min_score:
            return ToolRiskLevel.HIGH
        if triage.risk_score >= RESPONSE_RISK_POLICY.medium_min_score:
            return ToolRiskLevel.MEDIUM
        return ToolRiskLevel.LOW

    def _boundary_decision(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> ResponseBoundaryDecision:
        basis = self._decision_basis(report, triage, event)
        has_knowledge_gap = bool(triage.evidence_gaps or report.unresolved_questions)
        has_tool_failure = any(
            step.tool_result is not None and step.tool_result.status != ToolCallStatus.SUCCESS
            for step in report.steps
        )

        if triage.response_evidence_scope is None:
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_continued_investigation=True,
                reason="缺少已冻结的 response_evidence_scope，按 fail-closed 处理",
                basis=basis,
            )

        if triage.response_evidence_scope == ResponseEvidenceScope.OUT_OF_SCOPE:
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.OUT_OF_SCOPE,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_manual_takeover=True,
                reason="事件信号合同标记为 out_of_scope，不生成 WebShell 处置动作",
                basis=basis,
            )

        if triage.response_evidence_scope == ResponseEvidenceScope.WEAK_SIGNAL:
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_continued_investigation=True,
                reason="事件信号合同标记为 weak_signal，只允许继续调查或人工接管",
                basis=basis,
            )

        if report.conclusion != TruthVerdict.MALICIOUS or triage.verdict != TruthVerdict.MALICIOUS:
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.OUT_OF_SCOPE,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_manual_takeover=True,
                reason="调查或分诊未确认恶意 WebShell",
                basis=basis,
            )

        if self._has_out_of_scope_signal(report, triage, event):
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.OUT_OF_SCOPE,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_manual_takeover=True,
                reason="证据指向非 WebShell 域，不生成 WebShell 处置动作",
                basis=basis,
            )

        if has_tool_failure or has_knowledge_gap:
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_continued_investigation=True,
                reason="存在工具失败、弱证据或知识缺口，只允许继续调查或人工接管",
                basis=basis,
            )

        if not self._has_webshell_signal(report, triage, event):
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_continued_investigation=True,
                reason="缺少明确 WebShell 范围信号，不能生成高风险处置",
                basis=basis,
            )

        if not self._has_sufficient_evidence(report, triage):
            return ResponseBoundaryDecision(
                evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
                max_allowed_risk_level=ToolRiskLevel.LOW,
                requires_continued_investigation=True,
                reason="证据引用不足，不能生成高风险处置",
                basis=basis,
            )

        return ResponseBoundaryDecision(
            evidence_scope=ResponseEvidenceScope.IN_SCOPE,
            max_allowed_risk_level=ToolRiskLevel.CRITICAL,
            reason="WebShell 范围和关键证据已满足候选处置边界",
            basis=basis,
        )

    def _decision_basis(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> tuple[str, ...]:
        basis = [
            f"triage.verdict={triage.verdict.value}",
            f"triage.risk_score={triage.risk_score}",
            f"triage.response_evidence_scope={triage.response_evidence_scope.value if triage.response_evidence_scope else 'unset'}",
            f"triage.supporting_evidence_refs={len(triage.supporting_evidence_refs)}",
            f"triage.evidence_gaps={len(triage.evidence_gaps)}",
            f"report.conclusion={report.conclusion.value}",
            f"report.key_evidence_refs={len(report.key_evidence_refs)}",
            f"report.unresolved_questions={len(report.unresolved_questions)}",
        ]
        if event is not None:
            basis.append(f"event.summary={event.summary}")
            basis.append(f"event.correlation_reason={event.correlation_reason}")
        return tuple(basis)

    def _has_webshell_signal(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> bool:
        text = self._combined_text(report, triage, event)
        return any(marker in text for marker in WEBSHELL_SCOPE_MARKERS)

    def _has_out_of_scope_signal(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> bool:
        text = self._combined_text(report, triage, event)
        has_oos = any(marker in text for marker in OUT_OF_SCOPE_MARKERS)
        has_strong_webshell = any(marker in text for marker in WEBSHELL_STRONG_MARKERS)
        return has_oos and not has_strong_webshell

    def _has_sufficient_evidence(self, report: InvestigationReport, triage: TriageResult) -> bool:
        evidence_refs = {ref for ref in [*triage.supporting_evidence_refs, *report.key_evidence_refs] if ref}
        return len(evidence_refs) >= 2

    def _combined_text(
        self,
        report: InvestigationReport,
        triage: TriageResult,
        event: SecurityEvent | None,
    ) -> str:
        parts = [
            triage.summary,
            *triage.supporting_evidence_refs,
            *triage.opposing_evidence_refs,
            *triage.evidence_gaps,
            report.summary,
            *report.key_evidence_refs,
            *report.evidence_relations,
            *report.unresolved_questions,
            *report.recommended_actions,
        ]
        if event is not None:
            parts.extend([event.summary, event.correlation_reason, *event.alert_refs])
        return " ".join(str(part).lower() for part in parts if part)

    def _risk_order(self, risk_level: ToolRiskLevel) -> int:
        order = {
            ToolRiskLevel.LOW: 1,
            ToolRiskLevel.MEDIUM: 2,
            ToolRiskLevel.HIGH: 3,
            ToolRiskLevel.CRITICAL: 4,
        }
        return order[risk_level]


class ResponseExecutionService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def execute(self, trace_id: str, event_id: str, plan: ResponsePlan, idempotency_key: str) -> ExecutionResult:
        if plan.risk_level in APPROVAL_RISK_LEVELS and not plan.approval_required:
            raise ValueError("中高风险处置动作必须保留审批门禁")
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
            effect_layer=VerificationEvidenceLayer.STATEFUL_MOCK,
            error=result.error_type.value if result.error_type else None,
            retry_count=0,
            idempotency_key=idempotency_key,
        )


class ResponseVerificationService:
    def __init__(self, platform: PlatformAdapter) -> None:
        self._platform = platform

    def verify(self, trace_id: str, event_id: str, execution: ExecutionResult) -> VerificationResult:
        if not execution.executed or execution.status != ToolCallStatus.SUCCESS:
            return VerificationResult(
                status=VerificationStatus.INEFFECTIVE,
                method="执行结果显示处置工具未成功，未进入生效证明",
                verified_effect_layer=execution.effect_layer,
                evidence_refs=[],
                adjustment_suggestion="处置工具失败，不能写成处置已生效，需要人工接管",
                final_status=BusinessStatus.HUMAN_REQUIRED,
            )

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
        effect_layer = self._verified_effect_layer(result.output_preview, execution)
        if effect_layer == VerificationEvidenceLayer.DEVICE_EFFECT and action_status in {"effective", "executed"}:
            final_status = BusinessStatus.COMPLETED
            verification_status = VerificationStatus.EFFECTIVE
            adjustment_suggestion = None
        elif action_status in {"failed", "ineffective"}:
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
            adjustment_suggestion = "未取得设备实际生效证据，需要人工接管"
        return VerificationResult(
            status=verification_status,
            method="通过平台适配器查询有状态 Mock 处置记录",
            verified_effect_layer=effect_layer,
            evidence_refs=result.evidence_refs,
            adjustment_suggestion=adjustment_suggestion,
            final_status=final_status,
        )

    def _verified_effect_layer(
        self,
        output_preview: dict,
        execution: ExecutionResult,
    ) -> VerificationEvidenceLayer:
        value = str(output_preview.get("effect_layer") or output_preview.get("verified_effect_layer") or "")
        for layer in VerificationEvidenceLayer:
            if value == layer.value:
                return layer
        if execution.mode == ExecutionMode.MOCK:
            return VerificationEvidenceLayer.STATEFUL_MOCK
        return VerificationEvidenceLayer.PLATFORM_RECORD
