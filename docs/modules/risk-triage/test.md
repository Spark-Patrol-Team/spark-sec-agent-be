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

