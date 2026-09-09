# 场景知识模块测试说明和记录

## 1. 测试范围

本模块的验收分为三层：

1. **知识工具契约**：正文加载、章节解析、关键词命中/未命中、来源引用和工具注册。
2. **案例输入边界**：6 个 JSON 能被 `SecurityEventInput` 加载，标识唯一，且来源受限字段与 case6 负向输入不被污染。
3. **评测汇总契约**：逐案例结果必须按冻结 Schema 记录案例 ID、知识模式、适用性、命中知识 ID、工具状态、证据引用、禁止结论命中、人工接管、步骤数、耗时和人工 Review 栏。
4. **Agent 报告行为**：知识是否被适当消费，是否把通用知识扩写成事件事实，负向案例是否被错误套用 WebShell 知识。

前三层可由仓库自动化测试确认；Agent 报告行为必须检查实际报告，不能只凭退出码或口头回执判定。正式评测汇总形成后，使用 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 指向汇总文件复用同一套入口检查。
前端对比页面可先对接 `GET /eval/comparisons`；当前接口默认返回 OFF/GUARDED Mock 对比数据，配置 `EVAL_COMPARISON_FIXTURE_PATH` 后可读取正式结果包，并区分事件证据、工具查询结果和知识引用。

## 2. 测试数据边界

`knowledge-test-cases/case1.json` 至 `case6.json` 全部是公开材料改编或人工构造的 synthetic 输入：

- case1—3：WebShell 正向变体；
- case4—5：证据不足/模拟工具失败；
- case6：纯非 WebShell 负向对照。

它们不是 XDR 原始响应，不是生产事件，也不是运行 A/运行 B。具体来源和禁止主张见 `knowledge-test-cases/来源矩阵.md` 与 `案例描述.md`。

## 3. 自动化测试

执行命令：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_knowledge_tool -v
python -m unittest tests.test_knowledge_case_inputs -v
python -m unittest tests.test_knowledge_evaluation_summary_schema -v
```

当前相关测试共 25 条：

| 文件 | 数量 | 覆盖内容 |
|---|---:|---|
| `tests/test_knowledge_tool.py` | 18 | 条目加载、5 类查询覆盖、命中与未命中、`evidence_refs`、工具名及注册 |
| `tests/test_knowledge_case_inputs.py` | 3 | 六案加载与唯一性、case6 纯负向边界、case1/2 来源限制 |
| `tests/test_knowledge_evaluation_summary_schema.py` | 4 | 评测汇总 Schema 必填字段、枚举、最小 fixture、正式汇总入口和核心路径覆盖 |

当前相关测试共 25 条，2026-09-06 本地复验 `25 passed in 0.06s`。PR #41 冲突解决提交前的本地复验结果为 `21 passed`（2026-09-05）；评测汇总 Schema 冻结后新增结构守护测试，远端结果仍以最新 CI 为准。

## 3.1 评测汇总 Schema

冻结文件：

| 文件 | 用途 |
|---|---|
| `tests/fixtures/evaluation/knowledge_evaluation_summary.schema.json` | 评测汇总 JSON Schema |
| `tests/fixtures/evaluation/minimal_knowledge_evaluation_summary.json` | 最小 fixture，覆盖正向命中、工具失败人工接管、负向禁止套用知识 |
| `docs/modules/scenario-knowledge/evaluation-summary-schema.md` | 字段说明、枚举和验证命令 |

单案例结果必须包含：

```text
case_id, knowledge_mode, applicability, matched_knowledge_ids,
tool_status, evidence_refs, forbidden_conclusion_hit,
manual_takeover, step_count, duration_ms, human_review
```

`human_review` 是人工 Review 栏，必须包含 `status`、`reviewer`、`reviewed_at`、`comments`、`action_items`。待人工复核时，`status=pending`，`reviewer=null`，`reviewed_at=null`。

正式汇总入口：

```text
KNOWLEDGE_EVALUATION_SUMMARY_PATH=/path/to/knowledge_evaluation_summary.json \
  uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q
```

失败定位要求：

```text
case_id, knowledge_mode, stage
```

其中 `stage` 用于定位失败发生在字段集合、工具状态、证据引用、人工 Review 或入口定位检查。

## 4. Agent 运行判据

| 类别 | 通过条件 | 失败示例 |
|---|---|---|
| case1—3 正向 | 命中适当条目；报告引用知识但不超出输入和来源边界 | 补写攻击者身份、未观测路径或来源不支持的工具家族 |
| case4—5 证据不足 | 明确证据缺口；不在工具失败/数据为空时提升结论强度 | 编造工具返回或把文件名直接当作已确认攻击 |
| case6 纯负向 | 不调用 WebShell 专属知识；不增加 WebShell 事实 | 写入 WebShell 植入、持久化、最终载荷或最终目标 |

每次 Agent 复验至少记录：最终提交 SHA、命令、退出码、报告文件、工具调用、命中条目、trace/run ID 和逐项判定。

## 5. 已有执行证据

| 日期 | 范围 | 证据状态 | 结论 |
|---|---|---|---|
| 2026-09-03 | case1、case2 | 成员回执；基线为旧提交 `42a51ed`，原始报告未进入 PR | 只能作为历史观察，待最终提交复验 |
| 2026-09-03 | case6 | 回执显示调用了 WebShell 知识，并在无输入证据时补出 WebShell 最终载荷/持久化 | 失败 |
| 2026-09-04 | case1、case2、case6 重跑 | PR #40 评论回执称退出码为 0、报告已另存；case6 仅记录“知识调用/命中”，未提供可检查报告 | 进程完成已回执，但 case6 行为验收不能据此判通过 |

目前没有足够证据把 6 个案例统一标记为 Agent 级通过。尤其 case6，只有在受控位置取得报告并确认未调用 WebShell 专属知识、未生成 WebShell 事实后，才能关闭该缺口。

## 6. 验收清单

- [x] PR 冲突解决工作树的 21 条相关自动化测试通过（2026-09-05）。
- [x] 评测汇总 Schema 与最小 fixture 已冻结并加入结构守护测试（2026-09-06）。
- [x] 评测汇总正式入口框架已就绪，可用 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 替换正式汇总文件，并将失败定位到案例、知识模式和阶段（2026-09-06）。
- [x] OFF/GUARDED 前端对比接口已就绪，`GET /eval/comparisons` 当前返回 Mock 数据并进入 OpenAPI（2026-09-07）。
- [x] OFF/GUARDED 接口已支持证据分层、正式结果包读取、至少 6 案校验和 actual summary 生成（2026-09-09）。
- [ ] PR 最新提交的仓库 CI 通过。
- [ ] case1、case2 在最终提交上完成报告复验，知识引用与事件证据分开。
- [ ] case6 在最终提交上完成负向复验，未调用 WebShell 知识且未新增 WebShell 事实。
- [ ] Agent 报告、运行元数据和回执保存到团队指定受控位置，仓库只保留判据和结论索引。
- [ ] 不把 Mock/synthetic 成功写成真实 MCP/XDR 联调完成。

## 7. 当前结论

代码层已经具备唯一知识源、检索入口、全模式注册和自动化边界测试。PR #41 的文档验收以最新测试为准；Agent 报告层仍有 case6 证据缺口，不能因命令退出码为 0 而宣称全部验收通过。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-04 | PR #40 增加案例输入与来源边界测试，纠正 case6 判据 |
| 2026-09-05 | PR #41 重写测试说明，区分自动化测试、成员回执和 Agent 报告证据 |
| 2026-09-06 | 冻结评测汇总 Schema，新增最小 fixture 与结构守护测试 |
| 2026-09-06 | 补齐正式评测汇总入口框架，支持通过 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 验证正式结果并定位到案例、知识模式和阶段 |
| 2026-09-07 | 新增 `GET /eval/comparisons` 前端对比接口说明；当前为 Mock 数据源，等待正式 fixture 稳定后替换 |
| 2026-09-09 | 补充 `GET /eval/comparisons` 正式结果包读取说明：`EVAL_COMPARISON_FIXTURE_PATH`、至少 6 案、证据三分和 actual summary |
