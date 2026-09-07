# 知识评测汇总 Schema

## 1. 结论

知识评测汇总结构已冻结为：

- Schema：`tests/fixtures/evaluation/knowledge_evaluation_summary.schema.json`
- 最小 fixture：`tests/fixtures/evaluation/minimal_knowledge_evaluation_summary.json`
- 结构守护测试：`tests/test_knowledge_evaluation_summary_schema.py`

该 Schema 用于记录每个评测案例的知识使用情况、适用性、命中知识、工具状态、证据引用、禁止结论、人工接管、执行步数、耗时和人工 Review 栏。
正式评测汇总尚未生成前，测试入口默认使用最小 fixture；正式汇总形成后，通过 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 指向正式结果文件即可复用同一套结构守护测试。

## 2. 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | 是 | 固定为 `2026-09-06.knowledge-eval-summary.v1` |
| `evaluation_id` | string | 是 | 本次评测汇总 ID，格式为 `eval-YYYYMMDD-...` |
| `generated_at` | string | 是 | 汇总生成时间，ISO 8601 |
| `suite` | object | 是 | 评测套件信息 |
| `results` | array | 是 | 逐案例评测汇总行 |

## 3. 单案例结果字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | string | 是 | 案例 ID，如 `case1`、`case6` 或 `TC-...` |
| `knowledge_mode` | enum string | 是 | 知识模式 |
| `applicability` | enum string | 是 | 知识适用性 |
| `matched_knowledge_ids` | string array | 是 | 命中知识 ID；未命中或禁止调用时为空数组 |
| `tool_status` | object | 是 | 工具状态 |
| `evidence_refs` | string array | 是 | 报告或工具输出引用的证据 |
| `forbidden_conclusion_hit` | boolean | 是 | 是否命中禁止结论 |
| `manual_takeover` | boolean | 是 | 是否触发人工接管 |
| `step_count` | integer | 是 | 执行步骤数，未知时可填 0 |
| `duration_ms` | integer | 是 | 耗时毫秒，未知时可填 0 |
| `human_review` | object | 是 | 人工 Review 栏 |

## 4. 枚举

`knowledge_mode`：

| 值 | 含义 |
|---|---|
| `knowledge_required` | 本案例必须调用并使用知识 |
| `knowledge_optional` | 知识可作为参考，但不能替代证据 |
| `knowledge_forbidden` | 禁止套用当前知识，如 case6 纯非 WebShell 负向对照 |
| `knowledge_not_applicable` | 当前知识库不适用 |

`applicability`：

| 值 | 含义 |
|---|---|
| `applicable` | 知识适用 |
| `partially_applicable` | 部分适用 |
| `not_applicable` | 不适用 |
| `unknown` | 需要人工确认 |

`tool_status.knowledge_query` 和 `tool_status.mcp_tools`：

| 值 | 含义 |
|---|---|
| `success` | 调用成功 |
| `failed` | 调用失败 |
| `partial` | 部分成功 |
| `not_called` | 未调用 |
| `skipped` | 本轮明确跳过 |

`human_review.status`：

| 值 | 含义 |
|---|---|
| `pending` | 待人工 Review |
| `passed` | 人工 Review 通过 |
| `failed` | 人工 Review 不通过 |
| `needs_follow_up` | 需要补充材料或重跑 |

## 5. 固定知识 ID

| 知识 ID | 对应条目 |
|---|---|
| `K-WEBSHELL-PRINCIPLE` | 攻击原理 |
| `K-WEBSHELL-FEATURES` | 攻击特征速查表 |
| `K-WEBSHELL-TOOLS-TRAFFIC` | 主流管理工具与流量特征 |
| `K-WEBSHELL-EVIDENCE-CHECKLIST` | 证据检查清单 |
| `K-WEBSHELL-RESPONSE-TEMPLATE` | 处置建议模板 |
| `K-WEBSHELL-MANUAL-TAKEOVER` | 停止条件与人工接管规则 |

## 6. 最小 fixture 覆盖

`minimal_knowledge_evaluation_summary.json` 当前保留 3 条最小结果：

| case | 覆盖目的 |
|---|---|
| `case1` | 正向 WebShell 案例，必须命中知识 |
| `case5` | 模拟工具失败，要求人工接管 |
| `case6` | 纯非 WebShell 负向对照，禁止套用 WebShell 知识 |

该 fixture 只冻结结构和边界语义，不代表真实 MCP、真实 XDR 或真实处置已经执行。

## 7. 验证命令

验证默认最小 fixture：

```text
uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q
```

验证正式评测汇总：

```text
KNOWLEDGE_EVALUATION_SUMMARY_PATH=/path/to/knowledge_evaluation_summary.json \
  uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q
```

如需连同知识工具和案例输入一起验证：

```text
uv run pytest tests/test_knowledge_evaluation_summary_schema.py tests/test_knowledge_case_inputs.py tests/test_knowledge_tool.py -q
```

入口框架要求失败信息可定位到：

```text
case_id, knowledge_mode, stage
```

其中 `stage` 是校验阶段，例如 `result_contract`、`tool_status`、`evidence_refs`、`human_review` 或 `failure_locator`。
