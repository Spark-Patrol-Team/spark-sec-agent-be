# 场景知识模块测试说明和记录

## 0. 2026年9月13日最终收口候选复验

基线：PR #50原头`00e8115`；安全P0修复提交`6d363df`已于2026年9月13日以快进方式追加到PR #50远程源分支。

本轮新增或修正的自动化覆盖：

- 门禁`None`时知识工具返回`missing_knowledge_gate_decision`；
- `guarded`模式缺少合法门禁结果时，CLI和主链bridge均不注册`knowledge_query`；
- `out_of_scope`事件不向Agent暴露WebShell知识工具，避免域外案例产生知识调用；
- 正式CLI兼容case1—6扁平结构与case7—10的`input_event`包裹结构，避免包裹案例被解析为空事件；
- 合法`weak_signal`门禁注册的知识工具只能返回受限`partial`；
- 否定语义中的`cmd.exe`、`Process.Start`不产生强确认信号；
- SSH域外语境优先于偶然出现的通用进程词；
- 输入质量提示改为语义描述，不依赖Case 2/Case 10编号；
- WSK-002、WSK-011、WSK-014来源问题及WSK-013/014的case10越界关联已修正；
- `pyproject.toml`和`uv.lock`加入Windows所需`tzdata`。
- 真实主链的证据摘要按`ref_id→summary`映射，空摘要不会造成后续证据错配；
- 删除旧`KnowledgeEntry`测试链，加载、匹配、未命中和知识缺口测试统一走`KnowledgeCard`正式解析器。

实际命令与结果：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_knowledge_gate_contract.py tests/test_knowledge_mode.py tests/test_knowledge_cards.py tests/test_knowledge_tool.py tests/test_gatekeeper_case1_10.py tests/test_deep_agent_bridge.py -q
# 124 passed

.venv\Scripts\python.exe -m pytest -q
# 309 passed, 1 skipped, 1 warning
```

运行态工具注册复验：同一CLI入口读取正式样例后，case9工具列表包含`knowledge_query`，case10工具列表不包含`knowledge_query`；两次运行均因未配置本地真实MCP地址而只加载仓库内可用工具，该告警不影响门禁判定。

唯一warning来自Starlette TestClient对AnyIO旧别名的弃用提示，不影响本轮功能判定。跳过项仍须结合测试名和最终CI说明，不得笼统写成全部通过。

远程基线证据：PR #50头`ae5aea0`的GitHub Actions（run `34742258627`）曾以`314 passed, 1 skipped`通过。本轮删除6条只验证旧`KnowledgeEntry`链的测试，迁移并保留12条正式`KnowledgeCard`测试，同时新增1条证据ID映射回归，因此本地全仓数量调整为`309 passed, 1 skipped`；测试总数下降不代表正式运行路径覆盖减少。最终以本轮整改推送后的PR最新CI为准。

## 1. 测试范围

本模块的验收分为三层：

1. **知识工具契约**：正文加载、章节解析、关键词命中/未命中、来源引用和工具注册。
2. **案例输入边界**：10 个 JSON 能被 `SecurityEventInput` 加载，标识唯一，且来源受限字段与case6/case10负向输入不被污染。
3. **评测汇总契约**：逐案例结果必须按冻结 Schema 记录案例 ID、知识模式、适用性、命中知识 ID、工具状态、证据引用、禁止结论命中、人工接管、步骤数、耗时和人工 Review 栏。
4. **Agent 报告行为**：知识是否被适当消费，是否把通用知识扩写成事件事实，负向案例是否被错误套用 WebShell 知识。

前三层可由仓库自动化测试确认；Agent 报告行为必须检查实际报告，不能只凭退出码或口头回执判定。

## 2. 测试数据边界

`knowledge-test-cases/case1.json` 至 `case10.json` 全部是公开材料改编或人工构造的 synthetic 输入：

- case1—3：WebShell 正向变体；
- case4—5：证据不足/模拟工具失败；
- case6：纯非 WebShell 负向对照。
- case7：合法业务误报；case8：弱信号；case9：强证据组合；case10：SSH暴力破解域外负向。

它们不是 XDR 原始响应，不是生产事件，也不是运行 A/运行 B。具体来源和禁止主张见 `knowledge-test-cases/来源矩阵.md` 与 `案例描述.md`。

## 3. 自动化测试

执行命令：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_knowledge_tool -v
python -m unittest tests.test_knowledge_case_inputs -v
python -m unittest tests.test_knowledge_evaluation_summary_schema -v
```

当前三类基础相关测试共18条：

| 文件 | 数量 | 覆盖内容 |
|---|---:|---|
| `tests/test_knowledge_tool.py` | 12 | 15张结构化卡加载、ID/主题/受控别名匹配、未命中与知识缺口、来源、工具名及注册 |
| `tests/test_knowledge_case_inputs.py` | 3 | 六案加载与唯一性、case6 纯负向边界、case1/2 来源限制 |
| `tests/test_knowledge_evaluation_summary_schema.py` | 3 | 评测汇总 Schema 必填字段、枚举、最小 fixture 和核心路径覆盖 |

PR #41 冲突解决提交前的本地复验结果为 `21 passed`（2026-09-05）；评测汇总 Schema 冻结后新增 3 条结构守护测试，远端结果仍以最新 CI 为准。

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

上述内容是9月6日前的历史证据状态。9月11日团队已在受控位置收到10案×OFF/GUARDED共20份实际报告；是否按最终候选统一通过，仍需完成运行Commit绑定及闫昱硕、肖迎春的正式Review，不能仅凭收件或退出码判通过。

## 6. 验收清单

- [x] PR 冲突解决工作树的 21 条相关自动化测试通过（2026-09-05）。
- [x] 评测汇总 Schema 与最小 fixture 已冻结并加入结构守护测试（2026-09-06）。
- [x] PR #50安全P0代码及状态文档头`6f59e59`的仓库CI通过：`312 passed, 1 skipped`。
- [x] 杨嘉琪Review提出的证据ID/摘要错配已改为按ID映射；旧`KnowledgeEntry`解析链已删除；域外工具注册口径已同步。
- [ ] case1、case2 在最终提交上完成报告复验，知识引用与事件证据分开。
- [ ] case6 在最终提交上完成负向复验，未调用 WebShell 知识且未新增 WebShell 事实。
- [ ] Agent 报告、运行元数据和回执保存到团队指定受控位置，仓库只保留判据和结论索引。
- [ ] 不把 Mock/synthetic 成功写成真实 MCP/XDR 联调完成。

## 7. 当前结论

代码层已经具备唯一知识源、结构化检索入口、三档受控注册和自动化边界测试。2026-09-13提交`6d363df`已关闭门禁`None/异常`fail-open、通过全仓回归并追加到PR #50；最终验收仍需确认该PR最新CI和Review，并完成A/B报告与最终Commit的一致性复验。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-04 | PR #40 增加案例输入与来源边界测试，纠正 case6 判据 |
| 2026-09-05 | PR #41 重写测试说明，区分自动化测试、成员回执和 Agent 报告证据 |
| 2026-09-06 | 冻结评测汇总 Schema，新增最小 fixture 与结构守护测试 |
| 2026-09-13 | 最终收口候选新增fail-closed、正式样例输入归一化、否定语义、域外优先级和bridge门禁绑定回归；目标测试127项通过，全仓312项通过、1项跳过；CLI实测case9注册知识工具、case10不注册 |
| 2026-09-13 | 按杨嘉琪Review修复证据ID/摘要错配，新增空摘要错位复现；删除旧`KnowledgeEntry`测试链并迁移至唯一`KnowledgeCard`路径；同步域外事件不注册知识工具的接口口径 |
