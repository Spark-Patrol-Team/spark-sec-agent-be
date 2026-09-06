# 闫昱硕——评测判据与证据边界交付物

> 本目录存放 T0905-03「评测判据与证据边界」的正式交付物。判据基于陈敏 `PR#43` 的 case1-10 事件信号合同（`tests/fixtures/gatekeeper_cases/caseN.json`），与李雨妍的冻结评测汇总 Schema（`tests/fixtures/evaluation/knowledge_evaluation_summary.schema.json`）字段枚举对齐。

## 交付内容

| 文件 | 对应任务 | 说明 |
|---|---|---|
| `证据强弱与结论上限规则.md` | 交付物 #1 | 三档门禁上限 + 陈敏 6 级信号映射 + 规则表 |
| `case1.expected.json` ~ `case10.expected.json` | 交付物 #2 | 10 份正式判据（单独保存，不写入 `caseN.json`） |
| `来源主张边界review.md` | 交付物 #3 | 知识卡来源—主张核验与冲突清单（案例级） |
| `WSK来源主张边界review.md` | 交付物 #3 | 15 张 WSK 知识卡来源—主张边界 Review（9.6 交闫昱硕） |
| `指标口径与原始计数.md` | 交付物 #4 | 分母、原始计数、禁止宣称项 |
| `一致性review.md` | 交付物 #5/#6 | 与陈敏信号合同的一致性 Review + 已知限制 + A/B 研判影响结论登记 |

## 判据字段约定（与汇总 Schema 对齐）

判据 JSON 的字段取值尽量复用 `knowledge_evaluation_summary.schema.json` 的枚举：

- `knowledge_mode` ∈ `knowledge_required / knowledge_optional / knowledge_forbidden / knowledge_not_applicable`
- `applicability` ∈ `applicable / partially_applicable / not_applicable / unknown`
- `allowed/required/forbidden_knowledge_ids` 使用固定的 `K-WEBSHELL-*` 知识 ID
- `expected_tool_status.knowledge_query / mcp_tools` ∈ `success / failed / partial / not_called / skipped`
- `expected_scope` ∈ `in_scope / weak_signal / out_of_scope`（三档门禁）
- `signal_strength.expected_gate_overall` 使用陈敏 `SignalStrength` 枚举（`OUT_OF_SCOPE / IN_SCOPE_CONFIRMED / IN_SCOPE_WEAK / MIXED / BENIGN_LIKE / INDETERMINATE`）
- `human_required` 为 bool，`automatic_checks` 为可自动检查项列表

判据是“预期/ground truth”，与“逐案例实际结果”的汇总行不同；本目录不生成第二套冻结 Schema，字段命名与枚举对齐上述两个既有资产。

## 验证命令

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/test_yanyushuo_expected_judgments.py tests/test_gatekeeper_case1_10.py tests/test_signal_extraction.py -q
```

`test_yanyushuo_expected_judgments.py` 会：

1. 校验 10 份判据 JSON 均可解析、必填字段齐全、类型正确；
2. 校验枚举与冻结汇总 Schema 一致（knowledge_mode / applicability / 知识 ID / tool_status）；
3. 校验 `expected_scope`、`signal_strength` 合法；
4. 校验内部一致性（forbidden ∩ required = ∅；forbidden ∩ allowed 不为空时需说明；out_of_scope 案例禁命中知识）；
5. 校验 `case_file` 指向的 fixture 存在，且其 `case_id` 与判据一致。

## 状态

- ✅ 交付物 #1~#4 已完成；交付物 #3 已扩展为 15 张 WSK 卡边界 Review；
- ✅ 交付物 #5（一致性 Review）已完成；已记录陈敏 `feat/case-quality-check-and-tests` 对 triage / case3 RSA / benign / alerts+evidence 统一抽取的修复，以及仍待处理的 case2/case10 输入口径问题；
- ✅ 交付物 #6（≥6 案 A/B 研判影响结论）已完成登记（8/10 案），见 `一致性review.md` 第 5 节；含限制（mock 行为对照，无真实 LLM 风险分/置信度数值）与缺陷点（`fold_scope` fail-open、case7 误报档语义）。
