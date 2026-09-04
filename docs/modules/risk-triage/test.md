# 风险研判模块测试说明

## 测试范围

- 字段完整性：`verdict`、`confidence`、`risk_score`、`priority`、`supporting_evidence_refs`、`opposing_evidence_refs`、`evidence_gaps`、`should_investigate`、`summary` 均正确填充。
- 规则正确性：严重度 + 攻击类型 + 关联加成 + 平台种子分的合成与阈值判定。
- 主链接入：研判后能正确进入调查或结束分诊，状态机不越权流转。

## 测试入口

```bash
PYTHONPATH=src python -m pytest -q
```

（`unittest` 风格用例也可用 `python -m unittest discover -s tests` 运行。）

研判用例文件：`tests/test_triage.py`；主链状态用例：`tests/test_state_flow.py`。

## 本轮回归结果（2026-08-26）

全量测试（拉取最新 `main` 后）：`73 passed, 1 skipped`（跳过项为未配置 `LLM_API_KEY` 的深度调查 LLM 可选用例，非回归）。

字段与规则核对（`RiskTriageService` 直连 + 主链 `Orchestrator`）：

| 场景 | verdict | confidence | risk_score | priority | should_investigate | support | oppose | gaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_sample WebShell（2 条高危） | malicious | 0.85 | 85 | high | True | 2 | 0 | 0 |
| JSONL SQL注入（high/seed 80） | malicious | 0.85 | 80 | high | True | 7 | 0 | 0 |
| JSONL WebShell（critical/seed 95） | malicious | 0.85 | 95 | high | True | 7 | 0 | 0 |
| JSONL 横向移动（medium/seed 65） | uncertain | 0.65 | 65 | medium | True | 7 | 0 | 1 |
| 低风险误报（low/无 seed） | benign | 0.70 | 10 | low | False | 1 | 0 | 0 |

说明：

- `normalized` 与 `raw` 两种 JSONL 输入模式产出完全一致，原始告警标准化链路无回归。
- fixed_sample 主链状态线：`RECEIVED → CORRELATING → TRIAGED → INVESTIGATING → DECISION_READY → APPROVAL_REQUIRED`，研判结果可直接进入调查阶段。
- `opposing_evidence_refs` 当前固定为空，符合第一版规则限制。
- 最新主干将深度调查后端改为 `deep_agent`（LLM）优先、`tool_mock` 兜底，不影响研判输出字段与「研判→调查」的交接；`triage.py` 与 `TriageResult` 模型在本次合并中无改动。

## 关键边界测试（T0827-07，2026-08-27）

为收口 `VERDICT_CONFIDENCE` 固定档位与「固定值 / 经验阈值」占位，补充 12 个边界用例至 `tests/test_triage.py`。更新后全量测试：`85 passed, 1 skipped`（原 73 + 新增 12，跳过项不变）。全部通过，无回归。

| 用例 | 覆盖点 | 结果 |
|---|---|---|
| `test_unknown_severity_contributes_zero` | 缺失严重度：空串 / 中文等级 / 大小写空白 → 严重度计 0 分 | 通过 |
| `test_unknown_attack_type_contributes_zero` | 未知攻击类型（`other` / 未知值）→ 攻击类型计 0 分 | 通过 |
| `test_missing_severity_and_unknown_type_collapses_to_zero` | 严重度与攻击类型均缺失且无证据 → 归零 + 证据缺口 | 通过 |
| `test_threshold_exactly_70_is_malicious` | 高风险阈值上边界：`=70` → malicious / high / 调查 | 通过 |
| `test_threshold_just_below_70_is_uncertain` | `69` → uncertain / medium / 调查 | 通过 |
| `test_threshold_exactly_40_is_uncertain_investigates` | 中风险阈值下边界：`=40` → uncertain / medium / 调查 | 通过 |
| `test_threshold_just_below_40_is_benign` | `39` → benign / low / 不调查 | 通过 |
| `test_confidence_matches_verdict_tiers` | `VERDICT_CONFIDENCE` 固定档位：0.85 / 0.65 / 0.70，只随 verdict | 通过 |
| `test_non_benign_always_investigates` | 需调查条件：非 benign 一律应进入调查 | 通过 |
| `test_uncertain_without_evidence_has_both_gaps` | 证据不足 + uncertain → 双缺口 | 通过 |
| `test_evidence_present_has_no_gap` | 有证据且非 uncertain → 无缺口 | 通过 |
| `test_correlation_bonus_crosses_high_threshold` | 关联加成把 60 分推过 70 阈值（60+15=75） | 通过 |

> 边界结论：`risk_score == 70` 判 `malicious`、`== 40` 判 `uncertain`（含等号）；`< 40` 判 `benign` 且不调查；`confidence` 为固定档位；未映射严重度 / 未知攻击类型计 0 分，会让分数塌缩，属需在真实数据中重点观察的缺失处理路径。

## 合并后回归（2026-09-04）

合并 PR #38（研判干净分支）后，`main@1dfe58b` 基线：

```bash
PYTHONPATH=src python -m pytest tests/test_triage.py -q   # 20 passed
PYTHONPATH=src python -m pytest -q -rs                    # 162 passed, 1 skipped
```

跳过项为 `tests/test_investigation_agent.py:232`（未配置 `LLM_API_KEY` 的深度调查可选用例），与研判无关。说明：陈敏字段映射分支自报 `175 passed, 1 skipped`（含 58 项逐字段核对 + 25 条端到端契约测试），与研判干净分支基线口径不同，不冲突。

真实观测边界（与字段契约对齐后确认）：

| 事件 | verdict | confidence | risk_score | priority | should_investigate | event_type | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `evt-9b6df22d-…` | malicious | 0.85 | 80 | high | True | sql_injection（name 回退） | 规则分 60 = high(40)+sql(20)；`risk_score=80` 由 `risk_score_seed=80` 主导 |

## 分数边界

- `>= 70`：`malicious / high / should_investigate=True`
- `40 ~ 69`：`uncertain / medium / should_investigate=True`
- `< 40`：`benign / low / should_investigate=False`

## 回归要求

改 `triage.py` 或相关模型后，至少执行：

```bash
PYTHONPATH=src python -m pytest tests/test_triage.py tests/test_state_flow.py -v
PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

