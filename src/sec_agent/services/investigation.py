from __future__ import annotations

from sec_agent.domain.models import (
    ApprovalStatus,
    BusinessStatus,
    InvestigationReport,
    InvestigationStep,
    SecurityEvent,
    ToolRequest,
    ToolCallStatus,
    ToolRiskLevel,
    TriageResult,
    TruthVerdict,
)
from sec_agent.platforms.base import PlatformAdapter


class DeepInvestigationAgent:
    def __init__(self, platform: PlatformAdapter, max_steps: int = 3) -> None:
        self._platform = platform
        self._max_steps = max_steps

    def investigate(self, trace_id: str, event: SecurityEvent, triage: TriageResult) -> InvestigationReport:
        steps: list[InvestigationStep] = []
        request = ToolRequest(
            trace_id=trace_id,
            event_id=event.event_id,
            stage=BusinessStatus.INVESTIGATING,
            tool_name="evidence_lookup",
            action_name="query_related_evidence",
            params={
                "event_id": event.event_id,
                "alert_refs": event.alert_refs,
                "entities": event.entities,
            },
            reason="补充风险研判中的证据缺口",
            dry_run=True,
            idempotency_key=f"{event.event_id}:evidence_lookup:1",
            risk_level=ToolRiskLevel.LOW,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            timeout_seconds=30,
            max_attempts=1,
        )
        result = self._platform.run_tool(request)
        steps.append(
            InvestigationStep(
                step_no=1,
                goal="查询关联证据",
                tool_request=request,
                tool_result=result,
                observation=result.summary,
            )
        )

        needs_human = result.status != ToolCallStatus.SUCCESS or (
            len(steps) >= self._max_steps and bool(triage.evidence_gaps)
        )
        recommended_actions = []
        if triage.verdict == TruthVerdict.MALICIOUS and not needs_human:
            recommended_actions = ["隔离或下线可疑 WebShell 文件", "阻断可疑源 IP 访问", "复查 Web 服务进程链"]

        return InvestigationReport(
            conclusion=triage.verdict,
            final_confidence=min(0.9, triage.confidence + 0.12),
            timeline=["收到关联事件", "执行证据查询", "形成调查结论"],
            tool_results=[result.raw_result_ref] if result.raw_result_ref else [],
            key_evidence_refs=triage.supporting_evidence_refs,
            evidence_relations=["上传文件、HTTP 访问、进程链指向同一资产"] if recommended_actions else [],
            affected_objects=event.entities.get("assets", []),
            unresolved_questions=triage.evidence_gaps if needs_human else [],
            recommended_actions=recommended_actions,
            needs_human=needs_human,
            steps=steps,
            summary="深度调查完成，已形成结构化证据和处置建议",
        )
