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
- 严重度 `AlertRecord.raw_severity` 由上游 `severity:int` 分级映射（`≥90→critical/90`、`≥70→high/80`、`≥50→medium/65`、`<50→low/30`），中文等级回退，未映射落 `medium/65`。
- `alert_type` 由上游 `event_type` 6 层优先链（`threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name`）给出；`name` 回退含 `sql`+「注入」或 `sa账户密码 / SQL 查询`→`sql_injection`，未知强制落 `other`。
- 权重与阈值尚未用真实平台数据校准，属于第一版基线。

## 字段契约对齐（2026-09-04）

与陈敏《T0903-06 下游摘要（一）》确认后的口径：

- `risk_score` 可能由平台 `risk_score_seed` 主导：真实事件 `severity=70 → high/80`，即使 `event_type` 判为 `sql_injection`（攻击分 20、规则分 60），`risk_score=80` 仍由 `seed=80` 主导。`verdict / confidence / priority` 稳定，但「规则贡献 vs 种子贡献」需区分。
- 证据引用命名约两层：`supporting_evidence_refs`（`evidence_refs[].ref_id`）用 XDR API 原始名（如 `…:gptResultDescription`，无 `xdr_` 前缀）；原始值留存于 `scenario_fields.xdr_*`（如 `xdr_gptResultDescription`）。
- `attackState`（攻击状态 0/2）≠ `stage`/`xdr_stage`（阶段数值）；旧记录中的 `attackStage` 应更正为 `stage`。
- `source_device_name` 可非 `"XDR"`（`devSourceName[]` 优先，可回退回退至 `"XDR"`）；真实列表可混入 STA 来源告警。
- 单条真实事件（`evt-9b6df22d-…`）结论为 `malicious / 0.85 / 80 / high / 应调查`，仅为一次研判观察，不构成统计校准或阈值优化。

## 本轮字段与规则核对（2026-09-13）

基线：`origin/main@0001bbd`（`triage.py` 自 2026-08-23 未改动，主链调用点 `orchestrator.py` 自 2026-09-05 未改动）。核对方式：直连 `RiskTriageService` + 主链 `Orchestrator` 实跑 `tests/fixtures/fixed_alerts/` 固定样例，`investigation_backend=tool_mock`。

`TriageResult` 九个字段逐项核对（全部正常填充）：

| 样例 | verdict | confidence | risk_score | priority | supporting | opposing | gaps | should_investigate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_sample `webshell-001`（2 条 high WebShell） | malicious | 0.85 | 85 | high | 2 | 0 | 0 | True |
| JSONL `FIX-STA-SQLI-001`（high/seed 80） | malicious | 0.85 | 80 | high | 7 | 0 | 0 | True |
| JSONL `FIX-XDR-WEBSHELL-001`（critical/seed 95） | malicious | 0.85 | 95 | high | 7 | 0 | 0 | True |
| JSONL `FIX-STA-LATERAL-001`（medium/seed 65） | uncertain | 0.65 | 65 | medium | 7 | 0 | 1 | True |

`normalized` 与 `raw` 两种 JSONL 输入模式逐字段完全一致；与 2026-08-26 记录的同批样例数值一致（85 / 80 / 95 / 65），未观察到字段漂移。

规则边界探针（`RiskTriageService` 直连）：

| 输入 | verdict | confidence | risk_score | priority | should_investigate | evidence_gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `low` + `other`（无 seed） | benign | 0.70 | 10 | low | False | 0 |
| `medium` + `other`，seed=39 | benign | 0.70 | 39 | low | False | 0 |
| `medium` + `other`，seed=40 | uncertain | 0.65 | 40 | medium | True | 1 |
| `critical` + `other`，2 条告警（60+15） | malicious | 0.85 | 75 | high | True | 0 |
| 缺严重度 + 未知类型 + 无证据 | benign | 0.70 | 0 | low | False | 1（缺少可定位的原始证据引用） |

结论：输出字段语义与本文档一致，无新增、无缺失字段，阈值含等号语义（`>=70` high、`>=40` medium）保持不变；`opposing_evidence_refs` 恒空与 `confidence` 固定档位属「当前固定规则限制」，不是回归。

## 研判到调查的交接契约（2026-09-13 复核）

主链在 `TRIAGED` 之后按 `should_investigate` 分流：

- `True` → `INVESTIGATING`，并把 `TriageResult` 对象原样传入调查服务：`self._investigation.investigate(ctx.trace_id, event, ctx.triage, run_id=ctx.run_id)`。研判结果不需要二次转换即可直接进入调查阶段。
- `False` → `COMPLETED`，分诊结束、不进入调查，`ctx.investigation` 保持为空。

调查侧实际消费的研判字段（`DeepAgentBridge._to_deep_agent_input`）：

| 调查入口字段 | 取自研判 |
| --- | --- |
| `severity` | `triage.priority.value.upper()` |
| `evidence` | `triage.supporting_evidence_refs`（与 `event.evidence_summaries` 组合为描述） |
| `initial_verdict` | `triage.verdict.value` |
| `confidence` | `triage.confidence` |
| `triage` | `TriageResult.model_dump(mode="json")` 全量透传 |

`tool_mock` 调查后端同样消费 `verdict`、`confidence`（+0.12，上限 0.9）、`supporting_evidence_refs`、`evidence_gaps`。因此改 `TriageResult` 字段名或语义前，必须先同步三处消费点：`services/orchestrator.py`、`services/deep_agent_bridge.py`、`services/investigation.py`。

