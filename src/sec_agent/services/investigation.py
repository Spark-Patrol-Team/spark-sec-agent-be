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
from sec_agent.services.deep_agent_bridge import DeepAgentBridge, DeepAgentBridgeUnavailable


class DeepInvestigationAgent:
    def __init__(self, platform: PlatformAdapter, max_steps: int = 3, backend: str = "auto") -> None:
        self._platform = platform
        self._max_steps = max_steps
        if backend not in {"auto", "deep_agent", "tool_mock"}:
            raise ValueError(f"不支持的深度调查后端: {backend}")
        self._backend = backend
        self._deep_agent_bridge = DeepAgentBridge()

    def investigate(
        self,
        trace_id: str,
        event: SecurityEvent,
        triage: TriageResult,
        run_id: str = "",
    ) -> InvestigationReport:
        fallback_reason: str | None = None
        if self._backend in {"auto", "deep_agent"}:
            try:
                return self._deep_agent_bridge.investigate(trace_id, run_id, event, triage)
            except DeepAgentBridgeUnavailable as exc:
                if self._backend == "deep_agent":
                    return self._unavailable_report(event, triage, str(exc))
                fallback_reason = f"deep_agent 不可用，已回退内部工具调查子链: {exc}"
            except Exception as exc:
                if self._backend == "deep_agent":
                    return self._unavailable_report(event, triage, f"deep_agent 调查异常: {exc}")
                fallback_reason = f"deep_agent 调查异常，已回退内部工具调查子链: {exc}"

        return self._internal_tool_investigate(trace_id, event, triage, fallback_reason=fallback_reason)

    def _internal_tool_investigate(
        self,
        trace_id: str,
        event: SecurityEvent,
        triage: TriageResult,
        fallback_reason: str | None = None,
    ) -> InvestigationReport:
        steps: list[InvestigationStep] = []
        results = []
        for step_no, request in enumerate(self._build_internal_tool_requests(trace_id, event), start=1):
            if step_no > self._max_steps:
                break
            result = self._platform.run_tool(request)
            results.append(result)
            steps.append(
                InvestigationStep(
                    step_no=step_no,
                    goal=self._tool_goal(request),
                    tool_request=request,
                    tool_result=result,
                    observation=result.summary,
                )
            )

        has_failed_tool = any(result.status != ToolCallStatus.SUCCESS for result in results)
        needs_human = has_failed_tool or (
            len(steps) >= self._max_steps and bool(triage.evidence_gaps)
        )
        recommended_actions = []
        if triage.verdict == TruthVerdict.MALICIOUS and not needs_human:
            recommended_actions = ["限制受影响资产的可疑入口", "阻断可疑源 IP 或会话", "复查关联日志与进程/账号活动"]

        unresolved_questions = triage.evidence_gaps if needs_human else []
        if fallback_reason:
            unresolved_questions = [fallback_reason, *unresolved_questions]

        timeline = ["收到关联事件"]
        if fallback_reason:
            timeline.append("deep_agent 未完成调查，回退内部工具调查子链")
        timeline.extend(step.goal for step in steps)
        timeline.append("形成调查结论")

        summary = "内部工具调查子链完成，已形成结构化证据和处置建议"
        if fallback_reason:
            summary = f"{summary}；{fallback_reason}"

        return InvestigationReport(
            conclusion=triage.verdict,
            final_confidence=min(0.9, triage.confidence + 0.12),
            timeline=timeline,
            tool_results=[result.raw_result_ref for result in results if result.raw_result_ref],
            key_evidence_refs=self._unique_refs(
                [*triage.supporting_evidence_refs, *(ref for result in results for ref in result.evidence_refs)]
            ),
            evidence_relations=self._evidence_relations(event, bool(recommended_actions)),
            affected_objects=event.entities.get("assets", []),
            unresolved_questions=unresolved_questions,
            recommended_actions=recommended_actions,
            needs_human=needs_human,
            steps=steps,
            summary=summary,
        )

    def _build_internal_tool_requests(self, trace_id: str, event: SecurityEvent) -> list[ToolRequest]:
        common_params = {
            "event_id": event.event_id,
            "alert_refs": list(event.alert_refs),
            "entities": event.entities,
        }
        return [
            ToolRequest(
                trace_id=trace_id,
                event_id=event.event_id,
                stage=BusinessStatus.INVESTIGATING,
                tool_name="evidence_lookup",
                action_name="query_related_evidence",
                params=common_params,
                reason="补充风险研判中的证据缺口",
                dry_run=True,
                idempotency_key=f"{event.event_id}:evidence_lookup:1",
                risk_level=ToolRiskLevel.LOW,
                approval_status=ApprovalStatus.NOT_REQUIRED,
                timeout_seconds=30,
                max_attempts=1,
            ),
            ToolRequest(
                trace_id=trace_id,
                event_id=event.event_id,
                stage=BusinessStatus.INVESTIGATING,
                tool_name="xdr_log_query",
                action_name="query_builtin_xdr_log",
                params={
                    **common_params,
                    "first_seen_at": event.first_seen_at.isoformat(),
                    "last_seen_at": event.last_seen_at.isoformat(),
                },
                reason="查询内置 XDR 样例日志，补充调查上下文",
                dry_run=True,
                idempotency_key=f"{event.event_id}:xdr_log_query:1",
                risk_level=ToolRiskLevel.LOW,
                approval_status=ApprovalStatus.NOT_REQUIRED,
                timeout_seconds=30,
                max_attempts=1,
            ),
        ]

    def _tool_goal(self, request: ToolRequest) -> str:
        if request.tool_name == "evidence_lookup":
            return "查询关联证据"
        if request.tool_name == "xdr_log_query":
            return "查询 XDR 样例日志"
        return f"执行调查工具 {request.tool_name}"

    def _evidence_relations(self, event: SecurityEvent, has_actions: bool) -> list[str]:
        if not has_actions:
            return []
        sources = ",".join(event.entities.get("src_ips", [])) or "未知来源"
        targets = ",".join(event.entities.get("assets", [])) or ",".join(event.entities.get("dst_ips", [])) or "未知资产"
        return [f"告警证据、XDR 样例日志与关联实体指向同一风险对象；来源 {sources}，目标 {targets}"]

    def _unique_refs(self, refs: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for ref in refs:
            if ref and ref not in seen:
                seen.add(ref)
                unique.append(ref)
        return unique

    def _unavailable_report(self, event: SecurityEvent, triage: TriageResult, reason: str) -> InvestigationReport:
        return InvestigationReport(
            conclusion=TruthVerdict.UNCERTAIN,
            final_confidence=max(0.1, min(0.6, triage.confidence)),
            timeline=["deep_agent 子智能体桥接失败"],
            tool_results=[],
            key_evidence_refs=list(triage.supporting_evidence_refs),
            evidence_relations=[],
            affected_objects=event.entities.get("assets", []) or event.entities.get("dst_ips", []),
            unresolved_questions=[reason, *triage.evidence_gaps],
            recommended_actions=["deep_agent 不可用，需要人工接管或切换 INVESTIGATION_BACKEND=auto/tool_mock"],
            needs_human=True,
            steps=[],
            summary=f"deep_agent 子智能体不可用: {reason}",
        )
