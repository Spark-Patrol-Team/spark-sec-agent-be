# 闫昱硕——评测判据与证据边界交付物

> 本目录存放 T0905-03「评测判据与证据边界」的正式交付物。判据基于陈敏 `PR#43` 门禁 + 沈洪旭 `PR#44` 的 case1-10 事件信号合同（`docs/modules/scenario-knowledge/knowledge-test-cases/caseN.json`），与李雨妍的冻结评测汇总 Schema（`tests/fixtures/evaluation/knowledge_evaluation_summary.schema.json`）字段枚举对齐。
>
> **PR 范围（2026-09-13，3.7 Review 第 1/2 项）**：本分支从最新 `main` 重建，只包含**判据、指标与 Review 材料**（本目录 + `tests/test_yanyushuo_expected_judgments.py`）；不夹带陈敏门禁、知识资产、case 输入或其他上游代码。

## 交付内容

| 文件 | 对应任务 | 说明 |
|---|---|---|
| `证据强弱与结论上限规则.md` | 交付物 #1 | 三档门禁上限 + 陈敏 6 级信号映射 + 规则表 |
| `case1.expected.json` ~ `case10.expected.json` | 交付物 #2 | 10 份正式判据（单独保存，不写入 `caseN.json`） |
| `来源主张边界review.md` | 交付物 #3 | 知识卡来源—主张核验与冲突清单（案例级） |
| `WSK来源主张边界review.md` | 交付物 #3 | 15 张 WSK 知识卡来源—主张边界 Review（9.6 交闫昱硕） |
| `指标口径与原始计数.md` | 交付物 #4 | 分母、原始计数、禁止宣称项 |
| `一致性review.md` | 交付物 #5/#6 | 与陈敏信号合同的一致性 Review + 已知限制 + A/B 研判影响结论登记 |
| `T0913-闫昱硕-正式ABReview与不通过项.md` | 交付物 #6 | 10 案正式 A/B Review + case6 越界判定 + 20 案 `need_manual_takeover` 解释 + 不通过项最小修改要求 |

## 判据字段约定（与汇总 Schema 对齐）

判据 JSON 的字段取值尽量复用 `knowledge_evaluation_summary.schema.json` 的枚举：

- `knowledge_mode` ∈ `knowledge_required / knowledge_optional / knowledge_forbidden / knowledge_not_applicable`
- `applicability` ∈ `applicable / partially_applicable / not_applicable / unknown`
- `allowed/required/forbidden_knowledge_ids` 使用固定的 `K-WEBSHELL-*` 知识 ID
- `knowledge_ids_wsk` 绑定**最终** `WSK-*` 知识卡（`WSK-001` ~ `WSK-015`）：其 `allowed/required/forbidden` 与 `K-WEBSHELL-*` 六组展开逐一对应。展开规则：

  | `K-WEBSHELL-*` 组（冻结 Schema 兼容层） | 展开为最终 `WSK-*` 卡 |
  |---|---|
  | `K-WEBSHELL-PRINCIPLE` | `WSK-001`、`WSK-013` |
  | `K-WEBSHELL-FEATURES` | `WSK-005`、`WSK-006`、`WSK-007` |
  | `K-WEBSHELL-TOOLS-TRAFFIC` | `WSK-009`、`WSK-014` |
  | `K-WEBSHELL-EVIDENCE-CHECKLIST` | `WSK-002`、`WSK-003`、`WSK-004`、`WSK-008`、`WSK-010` |
  | `K-WEBSHELL-RESPONSE-TEMPLATE` | `WSK-015` |
  | `K-WEBSHELL-MANUAL-TAKEOVER` | `WSK-011`、`WSK-012` |

  > WSK 级 `required` 的语义是「对应知识组需被覆盖（组内任一卡命中即满足组要求）」；保留 `K-WEBSHELL-*` 是为了兼容李雨妍已冻结的汇总 Schema，若后续 Schema 升级到 WSK 级，可直接以 `knowledge_ids_wsk` 为准。
- `expected_tool_status.knowledge_query / mcp_tools` ∈ `success / failed / partial / not_called / skipped`
- `expected_scope` ∈ `in_scope / weak_signal / out_of_scope`（三档门禁）
- `signal_strength.expected_gate_overall` 使用陈敏 `SignalStrength` 枚举（`OUT_OF_SCOPE / IN_SCOPE_CONFIRMED / IN_SCOPE_WEAK / MIXED / BENIGN_LIKE / INDETERMINATE`）
- `human_required` 为 bool，`automatic_checks` 为可自动检查项列表

判据是“预期/ground truth”，与“逐案例实际结果”的汇总行不同；本目录不生成第二套冻结 Schema，字段命名与枚举对齐上述两个既有资产。

## 验证命令

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/test_yanyushuo_expected_judgments.py -q
```

`test_yanyushuo_expected_judgments.py` 会：

1. 校验 10 份判据 JSON 均可解析、必填字段齐全、类型正确；
2. 校验枚举与冻结汇总 Schema 一致（knowledge_mode / applicability / 知识 ID / tool_status）；
3. 校验 `expected_scope`、`signal_strength` 合法；
4. 校验内部一致性（forbidden ∩ required = ∅；forbidden ∩ allowed 不为空时需说明；out_of_scope 案例禁命中知识）；
5. 校验 `case_file` 指向的 fixture 存在，且其 `case_id` 与判据一致；
6. 校验 `knowledge_ids_wsk` 绑定的 `WSK-*` 卡真实存在于唯一知识源 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`，且与 `K-WEBSHELL-*` 组展开一致。

> 案例目录存在两种结构：`case1-6` 为扁平结构（文件本身就是 `SecurityEventInput`），`case7-10` 为包裹结构（`{"case_id", "category", "description", "input_event"}`）；判据测试已兼容二者。

## 状态

- ✅ 交付物 #1~#4 已完成；交付物 #3 已扩展为 15 张 WSK 卡边界 Review；
- ✅ 交付物 #5（一致性 Review）已完成；已记录陈敏 `feat/case-quality-check-and-tests` 对 triage / case3 RSA / benign / alerts+evidence 统一抽取的修复，以及 case2（已收敛为 PassiveNeuron 部署尝试被阻断）、case10（门禁以 `input_quality_issues` 保守标注误标）的闭环；
- ✅ 交付物 #6（≥6 案 A/B 研判影响结论）预演：见 `一致性review.md` 第 5.1-5.4 节（8/10 案，确定性 mock 行为对照，含限制与缺陷点）。
- ⛔ **旧「正式 A/B 已完成」结论已删除**（2026-09-13，3.7 Review 第 4 项）：该结论形成时未取得 actual 运行包，不再作为交付物 #6 的正式结论（原 5.5 节内容已迁移）。
- ✅ **交付物 #6 正式 Review（重做）**：见 `T0913-闫昱硕-正式ABReview与不通过项.md`，基于杨景凡 `T0905-07` 正式 10 案 guarded/off 运行产物（脱敏汇总已入仓 `ab-results/T0905-07-OFF-GUARDED-AB-summary.json`，case6 已逐字核对原始报告）。结论：知识工具行为符合三档门禁、未观察到知识门禁越界；但 case6 报告攻击链/处置建议出现 WebShell 越界、20/20 `need_manual_takeover` 无区分度、处置链 NOT VERIFIED——已登记不通过项与最小修改要求。
- ⚠️ 证据边界：原始 20 份 `report_*.json` 含内网测试 IP 与平台数据快照，按作者“勿提交 Git”说明**不入仓**；仅脱敏 `_summary.json` 入仓。
