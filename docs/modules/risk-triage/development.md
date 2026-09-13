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

## 本轮核对与回归（2026-09-13）

基线 `origin/main@0001bbd`，核对分支 `docs/risk-triage-field-rule-mainchain-sync`（从最新 main 干净重建）。

```bash
PYTHONPATH=src python -m pytest tests/test_triage.py -q                            # 20 passed
PYTHONPATH=src python -m pytest tests/test_state_flow.py tests/test_run_flow.py -q  # 9 passed
PYTHONPATH=src python -m pytest -q -rs                                              # 309 passed, 1 skipped
PYTHONPATH=src python -m sec_agent.scripts.run_flow                                  # 主流程跑到 COMPLETED
```

- 跳过项为 `tests/test_investigation_agent.py:232`（未配置 `LLM_API_KEY` 的深度调查可选用例），与研判无关。
- 逐字段值与边界探针结果见 `test.md`「本轮回归结果（2026-09-13）」与 `design.md`「本轮字段与规则核对（2026-09-13）」。

近期合并影响评估：

- `triage.py` 最后改动为 2026-08-23（`3c4cd6f`），主链调用点 `orchestrator.py` 最后改动为 2026-09-05。
- 2026-09-06 之后 main 上的合并（调查桥接装配、深度调查后端切换、知识门禁 PR#50 fail-open 修复、case3 输入来源对齐）均未触及研判评分逻辑，也未改动「研判→调查」交接字段；门禁信号在调查主链的透传修复属于调查侧改动。
- 同一批固定样例字段值与本文件 2026-08-26 记录完全一致（85 / 80 / 95 / 65），`normalized` / `raw` 两种输入模式一致，未观察到字段或规则回归。
- `tool_mock` 后端下横向移动样例终点为 `HUMAN_REQUIRED`（调查侧判定证据不足需人工接管），属下游行为，不是研判回归。

## 待补充

- 用真实 STA/XDR 样本校准权重与阈值（当前仅有 1 次真实事件观察，不构成校准）。
- 反对证据规则：`opposing_evidence_refs` 仍固定为空，尚无反对证据模型。
- `confidence` 仍为按结论的固定档位（0.85 / 0.65 / 0.70），未与证据强弱挂钩。
- 规则命中明细与因子拆分的展示模型（需先扩展 `TriageResult`，再同步三处消费点）。

