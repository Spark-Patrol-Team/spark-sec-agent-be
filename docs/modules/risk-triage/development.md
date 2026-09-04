# 风险研判模块开发说明

## 代码位置

- 核心实现：`src/sec_agent/services/triage.py`（`RiskTriageService`）
- 输出模型：`src/sec_agent/domain/models.py`（`TriageResult`、`TruthVerdict`、`Priority`）
- 调用方：`src/sec_agent/services/orchestrator.py`（`Orchestrator.start`）

## 接入方式

`Orchestrator` 在「告警关联」之后调用：

```text
correlate(alerts) -> SecurityEvent
  -> triage(event, alerts) -> TriageResult
  -> 若 should_investigate 则进入 INVESTIGATING，否则 COMPLETED
```

调用点：

```python
ctx.triage = self._triage.triage(event, alerts)
ctx = self._move(ctx, BusinessStatus.TRIAGED, "完成风险研判")
if not ctx.triage.should_investigate:
    return self._move(ctx, BusinessStatus.COMPLETED, "低风险或明确误报，分诊结束")
ctx = self._move(ctx, BusinessStatus.INVESTIGATING, "进入深度调查")
```

## 依赖字段约定

- `AlertRecord.raw_severity`：上游 `severity:int` 分级映射（`≥90 critical`、`≥70 high`、`≥50 medium`、`<50 low`），中文等级回退；未映射落 `medium`。对应的 `risk_score_seed`（`critical/90`、`high/80`、`medium/65`、`low/30`）。
- `AlertRecord.alert_type`：上游 `event_type` 6 层优先链（`threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name`）；`name` 回退含 `sql`+「注入」或 `sa账户密码 / SQL 查询`→`sql_injection`，未知落 `other`。
- `AlertRecord.evidence_refs`：写入 `supporting_evidence_refs`。
- `AlertRecord.scenario_fields["risk_score_seed"]`：可选平台种子分（0~100 整数）。
- （可选）`scenario_fields.xdr_*`：原始 XDR 字段留存（如 `xdr_gptResultDescription`、`xdr_attackState`、`xdr_confidence`、`xdr_stage`），仅供人工研判/调查参考，不参与当前确定性打分。
- `SecurityEvent.alert_count_before`：关联前告警数，触发关联加成。

## 修改注意

- 保持输出与 `TriageResult` 模型一致，不要新增不存在的解释字段；如需展示，先扩展模型再改。
- 不要只转述一次大模型问答，必须保留确定性规则基线。
- 不直接执行处置，不直接修改业务状态。
- 修改阈值/权重时同步更新 `design.md` 与 `test.md`，并跑通 `tests/test_triage.py`。

## 待补充

- 用真实 STA/XDR 样本校准权重与阈值。
- 反对证据规则。
- 规则命中明细与因子拆分的展示模型。

