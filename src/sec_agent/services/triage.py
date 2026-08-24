from __future__ import annotations

from sec_agent.domain.models import AlertRecord, Priority, SecurityEvent, TriageResult, TruthVerdict


# 第一版确定性规则基线的评分参数。字段以当前仓库模型为准，权重/阈值待用固定样例校准。
SEVERITY_POINTS = {"critical": 60, "high": 40, "medium": 20, "low": 10}
ATTACK_TYPE_POINTS = {
    "webshell": 30,
    "unauthorized_access": 25,
    "sql_injection": 20,
    "lateral_movement": 20,
}
CORRELATION_BONUS = 15
HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40

# 第一版置信度占位：按结论给确定性档位，后续用固定样例校准后替换。
VERDICT_CONFIDENCE = {
    TruthVerdict.MALICIOUS: 0.85,
    TruthVerdict.UNCERTAIN: 0.65,
    TruthVerdict.BENIGN: 0.70,
}


class RiskTriageService:
    """风险研判第一版：确定性规则评分（简单规则基线）。

    字段对齐结论（以当前仓库模型为联调基线，不新增字段）：
    - ``AlertRecord.raw_severity``          告警严重度（critical/high/medium/low）
    - ``AlertRecord.alert_type``            攻击类型（webshell / sql_injection / ...）
    - ``AlertRecord.scenario_fields["risk_score_seed"]``  平台提供的风险种子分（可选）
    - ``AlertRecord.evidence_refs``         证据引用（写入 supporting_evidence_refs）
    - ``SecurityEvent.alert_count_before``  关联前告警数（关联强度加成）

    输出结构与 ``TriageResult`` 保持一致，不新增规则命中、因子拆分等解释字段；
    如后续前端展示或评测确实需要，再单独补充。
    """

    def triage(self, event: SecurityEvent, alerts: list[AlertRecord]) -> TriageResult:
        rule_score = self._rule_score(alerts)
        if event.alert_count_before >= 2:
            rule_score += CORRELATION_BONUS

        seed = self._max_seed(alerts)
        risk_score = min(100, max(rule_score, seed if seed is not None else 0))

        supporting = [ref.ref_id for alert in alerts for ref in alert.evidence_refs]
        gaps: list[str] = []
        if not supporting:
            gaps.append("缺少可定位的原始证据引用")

        verdict, priority, should_investigate, summary = self._decide(risk_score)
        if verdict is TruthVerdict.UNCERTAIN:
            gaps.append("需要补充平台侧日志或上下文")

        return TriageResult(
            verdict=verdict,
            confidence=VERDICT_CONFIDENCE[verdict],
            risk_score=risk_score,
            priority=priority,
            supporting_evidence_refs=supporting,
            opposing_evidence_refs=[],
            evidence_gaps=gaps,
            should_investigate=should_investigate,
            summary=summary,
        )

    def _rule_score(self, alerts: list[AlertRecord]) -> int:
        if not alerts:
            return 0
        severity = max((SEVERITY_POINTS.get(a.raw_severity.lower(), 0) for a in alerts), default=0)
        attack_type = max((ATTACK_TYPE_POINTS.get(a.alert_type, 0) for a in alerts), default=0)
        return severity + attack_type

    def _max_seed(self, alerts: list[AlertRecord]) -> int | None:
        seeds: list[int] = []
        for alert in alerts:
            value = alert.scenario_fields.get("risk_score_seed")
            if isinstance(value, int) and 0 <= value <= 100:
                seeds.append(value)
        return max(seeds) if seeds else None

    def _decide(self, risk_score: int) -> tuple[TruthVerdict, Priority, bool, str]:
        if risk_score >= HIGH_RISK_THRESHOLD:
            return (
                TruthVerdict.MALICIOUS,
                Priority.HIGH,
                True,
                "规则基线判断为高风险，需要进入深度调查补充证据并生成处置建议",
            )
        if risk_score >= MEDIUM_RISK_THRESHOLD:
            return (
                TruthVerdict.UNCERTAIN,
                Priority.MEDIUM,
                True,
                "规则基线判断证据不足，需要进入深度调查",
            )
        return (
            TruthVerdict.BENIGN,
            Priority.LOW,
            False,
            "规则基线判断为低风险或疑似误报，可结束分诊",
        )
