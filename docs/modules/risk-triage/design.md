# 风险研判模块设计

## 模块职责

对「告警关联」产出的安全事件及其原始告警列表执行第一版确定性规则评分，输出真实性判断、置信度、风险分、优先级、证据引用、证据缺口，以及是否进入深度调查。

## 输入输出

| 方向 | 类型 | 说明 |
| --- | --- | --- |
| 输入 | `SecurityEvent` | 关联后的安全事件，主要使用 `alert_count_before`（关联前告警数）和 `entities` |
| 输入 | `list[AlertRecord]` | 参与本次关联的原始告警，使用 `raw_severity`、`alert_type`、`evidence_refs`、`scenario_fields["risk_score_seed"]` |
| 输出 | `TriageResult` | 结构化的研判结果 |

`TriageResult` 字段语义：

| 字段 | 语义 |
| --- | --- |
| `verdict` | 真实性判断：`malicious` / `uncertain` / `benign` |
| `confidence` | 置信度（0~1），当前为按结论的固定档位 |
| `risk_score` | 风险分（0~100 整数） |
| `priority` | 优先级：`high` / `medium` / `low` |
| `supporting_evidence_refs` | 支持证据引用（来自告警的 `evidence_refs`） |
| `opposing_evidence_refs` | 反对证据引用（当前固定为空） |
| `evidence_gaps` | 证据缺口描述 |
| `should_investigate` | 是否进入深度调查 |
| `summary` | 研判结论摘要 |

## 评分规则

第一版为确定性规则基线，常量位于 `src/sec_agent/services/triage.py`：

| 常量 | 值 |
| --- | --- |
| 严重度分 | `critical=60`、`high=40`、`medium=20`、`low=10` |
| 攻击类型分 | `webshell=30`、`unauthorized_access=25`、`sql_injection=20`、`lateral_movement=20` |
| 关联加成 | `CORRELATION_BONUS=15`（`alert_count_before >= 2` 时） |
| 高风险阈值 | `70` |
| 中风险阈值 | `40` |
| 置信度 | `malicious=0.85`、`uncertain=0.65`、`benign=0.70` |

评分步骤：

1. `rule_score = 告警中最大严重度分 + 告警中最大攻击类型分`。
2. 若 `event.alert_count_before >= 2`，`rule_score += 15`。
3. 取告警中合法 `scenario_fields["risk_score_seed"]`（0~100 整数）的最大值作为平台种子分。
4. `risk_score = min(100, max(rule_score, seed或0))`。
5. 按阈值判定：

| 条件 | verdict | priority | should_investigate |
| --- | --- | --- | --- |
| `risk_score >= 70` | `malicious` | `high` | `True` |
| `40 <= risk_score < 70` | `uncertain` | `medium` | `True` |
| `risk_score < 40` | `benign` | `low` | `False` |

## 证据引用规则

- `supporting_evidence_refs` 收集所有告警 `evidence_refs` 的 `ref_id`。
- `opposing_evidence_refs` 当前固定为空（尚无反对证据模型）。
- 证据缺口：若无任何支持证据引用，追加「缺少可定位的原始证据引用」；若 `verdict=uncertain`，追加「需要补充平台侧日志或上下文」。

## 人工复核边界

研判本身不做人工复核决策，也不直接改业务状态或执行处置。它通过 `verdict=uncertain` 与 `evidence_gaps` 提供需要人工复核的线索；真正转人工由下游环节决定：

- 深度调查证据不足 → `HUMAN_REQUIRED`
- 无法形成可自动执行方案 → `HUMAN_REQUIRED`
- 高风险处置动作 → `APPROVAL_REQUIRED`
- 审批拒绝 → `HUMAN_REQUIRED`

## 当前固定规则限制

- 纯确定性规则，无机器学习 / 无大模型研判，仅保证可复现。
- `confidence` 是按结论的固定档位，未做校准。
- `opposing_evidence_refs` 始终为空。
- 不输出规则命中明细、因子拆分等解释字段（与当前 `TriageResult` 模型对齐）。
- 严重度依赖 `AlertRecord.raw_severity` 已标准化为 `critical/high/medium/low`；上游若给原始中文等级会按未知类型计 0 分。
- 权重与阈值尚未用真实平台数据校准，属于第一版基线。

