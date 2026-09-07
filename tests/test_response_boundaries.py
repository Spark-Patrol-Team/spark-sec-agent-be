import unittest

from sec_agent.domain.models import (
    BusinessStatus,
    ExecutionMode,
    ExecutionResult,
    InvestigationReport,
    Priority,
    ResponseEvidenceScope,
    ResponsePlan,
    SecurityEvent,
    ToolCallStatus,
    ToolErrorType,
    ToolRequest,
    ToolResult,
    ToolRiskLevel,
    VerificationEvidenceLayer,
    VerificationStatus,
    TriageResult,
    TruthVerdict,
    utc_now,
)
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.services.response import (
    ResponseDecisionService,
    ResponseExecutionService,
    ResponseVerificationService,
)


class ResponseBoundaryTest(unittest.TestCase):
    def test_confirmed_webshell_can_only_reach_approval_gate_for_high_risk_plan(self) -> None:
        plan = ResponseDecisionService().build_plan(
            self._confirmed_webshell_report(),
            self._triage(),
            self._event(),
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.evidence_scope, ResponseEvidenceScope.IN_SCOPE)
        self.assertEqual(plan.max_allowed_risk_level, ToolRiskLevel.CRITICAL)
        self.assertEqual(plan.risk_level, ToolRiskLevel.HIGH)
        self.assertTrue(plan.approval_required)

    def test_weak_evidence_does_not_generate_unconditional_high_risk_plan(self) -> None:
        report = self._confirmed_webshell_report(
            key_evidence_refs=["file-name-only", "file-path-only"],
            summary="仅发现 Web 目录存在 shell.php 文件名可疑，缺少访问和进程证据",
        )
        triage = self._triage(
            supporting_evidence_refs=["file-name-only", "file-path-only"],
            response_evidence_scope=ResponseEvidenceScope.WEAK_SIGNAL,
            risk_score=95,
        )

        plan = ResponseDecisionService().build_plan(report, triage, self._event(summary="WebShell 弱信号事件"))

        self.assertIsNone(plan)

    def test_out_of_scope_contract_does_not_generate_webshell_response_plan(self) -> None:
        plan = ResponseDecisionService().build_plan(
            self._confirmed_webshell_report(),
            self._triage(response_evidence_scope=ResponseEvidenceScope.OUT_OF_SCOPE, risk_score=95),
            self._event(),
        )

        self.assertIsNone(plan)

    def test_knowledge_gap_does_not_generate_unconditional_high_risk_plan(self) -> None:
        report = self._confirmed_webshell_report(
            unresolved_questions=["缺少文件内容分析和 HTTP 访问日志"],
        )
        triage = self._triage(evidence_gaps=["缺少进程/命令执行上下文"], risk_score=95)

        plan = ResponseDecisionService().build_plan(report, triage, self._event())

        self.assertIsNone(plan)

    def test_tool_failure_does_not_become_effective_verification(self) -> None:
        execution = ExecutionResult(
            executed=False,
            status=ToolCallStatus.FAILED,
            mode=ExecutionMode.REAL,
            platform_status="failed",
            effect_layer=VerificationEvidenceLayer.PLATFORM_REQUEST,
            error=ToolErrorType.PLATFORM_ERROR.value,
            idempotency_key="tool-failure-boundary",
        )

        verification = ResponseVerificationService(_LyingDeviceEffectPlatform()).verify(
            "trace-boundary",
            "evt-boundary",
            execution,
        )

        self.assertEqual(verification.status, VerificationStatus.INEFFECTIVE)
        self.assertEqual(verification.final_status, BusinessStatus.HUMAN_REQUIRED)
        self.assertNotEqual(verification.verified_effect_layer, VerificationEvidenceLayer.DEVICE_EFFECT)

    def test_non_webshell_does_not_generate_webshell_cleanup_action(self) -> None:
        report = self._confirmed_webshell_report(
            summary="SSH 暴力破解事件，未发现 Web 访问、脚本文件或 Web 进程异常",
            key_evidence_refs=["ssh-auth-log-001", "account-lockout-001"],
            evidence_relations=["SSH 登录失败日志与账号锁定记录指向同一来源 IP"],
            recommended_actions=["不要执行 WebShell 清除动作，转交账号安全处置"],
        )
        triage = self._triage(risk_score=95)

        plan = ResponseDecisionService().build_plan(
            report,
            triage,
            self._event(
                summary="已将 1 条 unauthorized_access 告警压缩为 1 个安全事件",
                correlation_reason="同一事件类型 unauthorized_access；SSH 暴力破解证据",
            ),
        )

        self.assertIsNone(plan)

    def test_malicious_non_webshell_with_high_score_and_sufficient_evidence_is_rejected(self) -> None:
        report = self._confirmed_webshell_report(
            summary="数据库凭据滥用事件，未发现脚本文件或应用层异常特征",
            key_evidence_refs=["db-login-001", "db-query-002"],
            evidence_relations=["数据库登录异常与高频查询行为指向同一资产"],
            recommended_actions=["转交数据库安全处置"],
        )
        triage = self._triage(
            summary="数据库凭据滥用高风险，需要继续深度调查",
            risk_score=95,
            supporting_evidence_refs=["db-login-001", "db-query-002"],
        )

        plan = ResponseDecisionService().build_plan(
            report,
            triage,
            self._event(
                summary="已将 1 条 database_abuse 告警压缩为 1 个安全事件",
                correlation_reason="同一事件类型 database_abuse；目标资产 db-server-01",
            ),
        )

        self.assertIsNone(plan)

    def test_approval_and_manual_takeover_are_not_bypassed_by_candidate_stage(self) -> None:
        service = ResponseDecisionService()
        high_risk_plan = service.build_plan(self._confirmed_webshell_report(), self._triage(), self._event())
        manual_report = self._confirmed_webshell_report(needs_human=True)

        self.assertIsNotNone(high_risk_plan)
        self.assertTrue(high_risk_plan.approval_required)
        self.assertIsNone(service.build_plan(manual_report, self._triage(), self._event()))

        tampered_plan = ResponsePlan(
            action="stateful_mock_containment",
            target="web-server-01",
            reason="测试篡改审批门禁",
            risk_level=ToolRiskLevel.HIGH,
            evidence_scope=ResponseEvidenceScope.IN_SCOPE,
            max_allowed_risk_level=ToolRiskLevel.CRITICAL,
            approval_required=False,
            rollback_available=True,
        )
        with self.assertRaisesRegex(ValueError, "审批门禁"):
            ResponseExecutionService(FixedSampleAdapter()).execute(
                "trace-boundary",
                "evt-boundary",
                tampered_plan,
                "approval-bypass-test",
            )

    def test_stateful_mock_success_does_not_prove_device_effect(self) -> None:
        plan = ResponseDecisionService().build_plan(self._confirmed_webshell_report(), self._triage(), self._event())
        self.assertIsNotNone(plan)

        adapter = FixedSampleAdapter()
        execution = ResponseExecutionService(adapter).execute(
            "trace-boundary",
            "evt-boundary",
            plan,
            "mock-success-boundary",
        )
        verification = ResponseVerificationService(adapter).verify(
            "trace-boundary",
            "evt-boundary",
            execution,
        )

        self.assertEqual(execution.effect_layer, VerificationEvidenceLayer.STATEFUL_MOCK)
        self.assertEqual(verification.verified_effect_layer, VerificationEvidenceLayer.STATEFUL_MOCK)
        self.assertEqual(verification.status, VerificationStatus.UNKNOWN)
        self.assertEqual(verification.final_status, BusinessStatus.HUMAN_REQUIRED)

    def test_platform_request_success_does_not_prove_device_effect(self) -> None:
        verification = ResponseVerificationService(
            _VerificationPlatform("accepted", VerificationEvidenceLayer.PLATFORM_REQUEST)
        ).verify("trace-boundary", "evt-boundary", self._real_execution(VerificationEvidenceLayer.PLATFORM_REQUEST))

        self.assertEqual(verification.verified_effect_layer, VerificationEvidenceLayer.PLATFORM_REQUEST)
        self.assertEqual(verification.status, VerificationStatus.UNKNOWN)
        self.assertEqual(verification.final_status, BusinessStatus.HUMAN_REQUIRED)

    def test_platform_record_success_does_not_prove_device_effect(self) -> None:
        verification = ResponseVerificationService(
            _VerificationPlatform("executed", VerificationEvidenceLayer.PLATFORM_RECORD)
        ).verify("trace-boundary", "evt-boundary", self._real_execution(VerificationEvidenceLayer.PLATFORM_RECORD))

        self.assertEqual(verification.verified_effect_layer, VerificationEvidenceLayer.PLATFORM_RECORD)
        self.assertEqual(verification.status, VerificationStatus.UNKNOWN)
        self.assertEqual(verification.final_status, BusinessStatus.HUMAN_REQUIRED)

    def test_device_effect_is_the_only_layer_that_can_complete_verification(self) -> None:
        verification = ResponseVerificationService(
            _VerificationPlatform("effective", VerificationEvidenceLayer.DEVICE_EFFECT)
        ).verify("trace-boundary", "evt-boundary", self._real_execution(VerificationEvidenceLayer.PLATFORM_RECORD))

        self.assertEqual(verification.verified_effect_layer, VerificationEvidenceLayer.DEVICE_EFFECT)
        self.assertEqual(verification.status, VerificationStatus.EFFECTIVE)
        self.assertEqual(verification.final_status, BusinessStatus.COMPLETED)

    def _triage(
        self,
        *,
        verdict: TruthVerdict = TruthVerdict.MALICIOUS,
        risk_score: int = 85,
        supporting_evidence_refs: list[str] | None = None,
        evidence_gaps: list[str] | None = None,
        response_evidence_scope: ResponseEvidenceScope | None = None,
        summary: str = "WebShell 高风险，需要深度调查",
    ) -> TriageResult:
        return TriageResult(
            verdict=verdict,
            confidence=0.85,
            risk_score=risk_score,
            priority=Priority.HIGH,
            response_evidence_scope=response_evidence_scope,
            supporting_evidence_refs=supporting_evidence_refs or ["evidence-http-001", "evidence-proc-001"],
            evidence_gaps=evidence_gaps or [],
            should_investigate=True,
            summary=summary,
        )

    def _confirmed_webshell_report(self, **overrides) -> InvestigationReport:
        data = {
            "conclusion": TruthVerdict.MALICIOUS,
            "final_confidence": 0.9,
            "key_evidence_refs": ["evidence-http-001", "evidence-proc-001"],
            "evidence_relations": ["异常 POST、WebShell 文件修改与 w3wp.exe 创建 cmd.exe 指向同一资产"],
            "affected_objects": ["web-server-01"],
            "recommended_actions": ["限制受影响资产的可疑入口"],
            "needs_human": False,
            "summary": "确认 WebShell 活动，已关联访问、文件和进程证据",
        }
        data.update(overrides)
        return InvestigationReport(**data)

    def _event(
        self,
        *,
        summary: str = "已将 2 条 webshell 告警压缩为 1 个安全事件",
        correlation_reason: str = "同一事件类型 webshell；目标资产 web-server-01",
    ) -> SecurityEvent:
        now = utc_now()
        return SecurityEvent(
            event_id="evt-boundary",
            alert_refs=["alert-1", "alert-2"],
            first_seen_at=now,
            last_seen_at=now,
            entities={"assets": ["web-server-01"]},
            correlation_reason=correlation_reason,
            alert_count_before=2,
            event_count_after=1,
            summary=summary,
        )

    def _real_execution(self, layer: VerificationEvidenceLayer) -> ExecutionResult:
        return ExecutionResult(
            executed=True,
            status=ToolCallStatus.SUCCESS,
            mode=ExecutionMode.REAL,
            platform_status="success",
            effect_layer=layer,
            idempotency_key="real-execution-boundary",
        )


class _VerificationPlatform:
    def __init__(self, action_status: str, effect_layer: VerificationEvidenceLayer) -> None:
        self._action_status = action_status
        self._effect_layer = effect_layer

    def fetch_alerts(self, sample_id=None, xdr_event_id=None):
        return []

    def run_tool(self, request: ToolRequest) -> ToolResult:
        return _tool_result(
            request,
            status=ToolCallStatus.SUCCESS,
            output_preview={
                "action_status": self._action_status,
                "effect_layer": self._effect_layer.value,
            },
            evidence_refs=[f"test://{self._effect_layer.value}/record"],
        )

    def query_action_status(self, idempotency_key: str) -> str:
        return self._action_status


class _LyingDeviceEffectPlatform(_VerificationPlatform):
    def __init__(self) -> None:
        super().__init__("effective", VerificationEvidenceLayer.DEVICE_EFFECT)


def _tool_result(
    request: ToolRequest,
    *,
    status: ToolCallStatus,
    output_preview: dict,
    evidence_refs: list[str] | None = None,
) -> ToolResult:
    started_at = utc_now()
    ended_at = utc_now()
    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        idempotency_key=request.idempotency_key,
        status=status,
        summary="边界测试平台返回",
        raw_result_ref="test://response-verify",
        evidence_refs=evidence_refs or [],
        output_refs=["test://response-verify"],
        output_preview=output_preview,
        retryable=False,
        platform_status=status.value,
        external_side_effect=False,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=1,
    )


if __name__ == "__main__":
    unittest.main()
