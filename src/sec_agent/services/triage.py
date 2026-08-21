from __future__ import annotations

from sec_agent.domain.models import AlertRecord, Priority, SecurityEvent, TriageResult, TruthVerdict


class RiskTriageService:
    def triage(self, event: SecurityEvent, alerts: list[AlertRecord]) -> TriageResult:
        score = 0
        supporting: list[str] = []
        gaps: list[str] = []

        high_count = sum(1 for alert in alerts if alert.raw_severity.lower() == "high")
        if high_count:
            score += min(40, high_count * 20)
            supporting.extend(ref.ref_id for alert in alerts for ref in alert.evidence_refs)

        if any(alert.alert_type == "webshell" for alert in alerts):
            score += 30

        if event.alert_count_before >= 2:
            score += 15

        if not supporting:
            gaps.append("缺少可定位的原始证据引用")

        if score >= 70:
            verdict = TruthVerdict.MALICIOUS
            priority = Priority.HIGH
            should_investigate = True
            summary = "规则基线判断为高风险，需要进入深度调查补充证据并生成处置建议"
        elif score >= 40:
            verdict = TruthVerdict.UNCERTAIN
            priority = Priority.MEDIUM
            should_investigate = True
            gaps.append("需要补充平台侧日志或上下文")
            summary = "规则基线判断证据不足，需要进入深度调查"
        else:
            verdict = TruthVerdict.BENIGN
            priority = Priority.LOW
            should_investigate = False
            summary = "规则基线判断为低风险或疑似误报，可结束分诊"

        return TriageResult(
            verdict=verdict,
            confidence=0.72 if should_investigate else 0.66,
            risk_score=min(100, score),
            priority=priority,
            supporting_evidence_refs=supporting,
            opposing_evidence_refs=[],
            evidence_gaps=gaps,
            should_investigate=should_investigate,
            summary=summary,
        )

