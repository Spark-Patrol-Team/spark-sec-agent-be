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

## 本轮核对与回归（2026-09-14主线复核）

基线`origin/main@787e737`，核对分支已合入该主线；该基线包含PR #50/#51/#58/#59/#60。

```bash
PYTHONPATH=src python -m pytest tests/test_triage.py tests/test_state_flow.py tests/test_run_flow.py tests/test_gatekeeper_boundary.py tests/test_response_boundaries.py -q  # 78 passed
PYTHONPATH=src python -m pytest -q -rs                                                                                                                   # 383 passed, 1 skipped, 1 warning
```

- 跳过项为`tests/test_investigation_agent.py:403`（未配置`LLM_API_KEY`的深度调查可选用例），与研判无关；1条warning来自Starlette TestClient依赖的弃用提示。
- 逐字段值、边界探针和最终状态见`test.md`“本轮回归结果（2026-09-14）”与`design.md`“本轮字段与规则核对（2026-09-14主线复核）”。

近期合并影响评估：

- `triage.py`最后改动仍为2026-08-23（`3c4cd6f`），研判评分值本轮未改变。
- PR #58/#59/#60更新了事件合同、知识门禁、域外报告约束和处置边界；`orchestrator.py`及`response.py`已在PR #60调整。它们没有修改研判分数，但会改变调查后的`response_evidence_scope`和主链终态。
- 同一批固定样例字段值与本文件 2026-08-26 记录完全一致（85 / 80 / 95 / 65），`normalized` / `raw` 两种输入模式一致，未观察到字段或规则回归。
- `tool_mock`后端实跑结果为：确认级固定WebShell样例进入`APPROVAL_REQUIRED`；仅有名称/类型线索的WebShell样例为`weak_signal → HUMAN_REQUIRED`；SQL注入和横向移动样例为`out_of_scope → HUMAN_REQUIRED`。这些是下游门禁/处置边界，不是研判评分回归。

## 待补充

- 用真实 STA/XDR 样本校准权重与阈值（当前仅有 1 次真实事件观察，不构成校准）。
- 反对证据规则：`opposing_evidence_refs` 仍固定为空，尚无反对证据模型。
- `confidence` 仍为按结论的固定档位（0.85 / 0.65 / 0.70），未与证据强弱挂钩。
- 规则命中明细与因子拆分的展示模型（需先扩展 `TriageResult`，再同步三处消费点）。

