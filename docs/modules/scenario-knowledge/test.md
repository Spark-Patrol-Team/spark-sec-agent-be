# 场景知识模块测试说明和记录

## 1. 测试范围

本模块的验收分为四层：

1. **知识工具契约**：正文加载、章节解析、关键词命中/未命中、来源引用和工具注册。
2. **案例输入与门禁边界**：`tests/fixtures/gatekeeper_cases/case1-10.json` 能被 `SecurityEventInput` 加载，标识唯一，且来源受限字段与负向输入不被污染。
3. **评测汇总契约**：逐案例结果必须按冻结 Schema 记录案例 ID、知识模式、适用性、命中知识 ID、工具状态、证据引用、禁止结论命中、人工接管、步骤数、耗时和人工 Review 栏。
4. **Agent 报告行为**：知识是否被适当消费，是否把通用知识扩写成事件事实，负向案例是否被错误套用 WebShell 知识。

前三层可由仓库自动化测试确认；Agent 报告行为必须检查实际报告，不能只凭退出码或口头回执判定。

## 2. 测试数据边界

`tests/fixtures/gatekeeper_cases/case1-10.json`（陈敏 PR#43）全部是公开材料改编或人工构造的 synthetic 输入：

- case1—3：WebShell 正向变体；
- case4—5：证据不足/模拟工具失败；
- case6：纯非 WebShell 负向对照；
- case7：合法上传误报（保留正常业务可能）；
- case8：仅文件名可疑弱信号；
- case9：异常 POST + 文件修改 + 进程创建组合（确认级）；
- case10：SSH 暴力破解域外负向。

它们不是 XDR 原始响应，不是生产事件，也不是运行 A/运行 B。具体来源和禁止主张见 `judgments/来源主张边界review.md`；10 案正式判据见 `judgments/caseN.expected.json`。

## 3. 自动化测试

执行命令：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_knowledge_tool -v
python -m pytest tests/test_gatekeeper_case1_10.py tests/test_signal_extraction.py tests/test_yanyushuo_expected_judgments.py tests/test_knowledge_evaluation_summary_schema.py -q
```

当前相关测试（知识工具 + 门禁 + 判据）：

| 文件 | 数量 | 覆盖内容 |
|---|---:|---|
| `tests/test_knowledge_tool.py` | 18 | 条目加载、5 类查询覆盖、命中与未命中、`evidence_refs`、工具名及注册 |
| `tests/test_gatekeeper_case1_10.py` | 71 | 门禁白名单、信号分类、case1-10 输入质量、信号标注、WebShell 专项升级、三方交接断言 |
| `tests/test_signal_extraction.py` | 12 | 案例质量、信号提取与分类逻辑 |
| `tests/test_yanyushuo_expected_judgments.py` | 7 | 10 判据结构、枚举对齐、内部一致性、case_file 指向、与陈敏期望强度对齐 |
| `tests/test_knowledge_evaluation_summary_schema.py` | 3 | 评测汇总 Schema 必填字段、枚举、最小 fixture 和核心路径覆盖 |

本地复验：`146 passed`（2026-09-06，含门禁/信号/判据/评测汇总/工具/契约回归）。远端结果以最新 CI 为准。

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

## 4. Agent 运行判据（依据闫昱硕 10 份正式判据）

| 类别 | 通过条件 | 失败示例 |
|---|---|---|
| 正向/确认（case1-3、case9） | 命中适当条目；报告引用知识但不超出输入和来源边界 | 补写攻击者身份、未观测路径、横向/窃取/持久化或来源不支持的工具家族 |
| 弱信号（case4-5、case7-8） | 明确证据缺口；只在弱口径下返回检查清单/误报条件；不在工具失败/数据为空时提升结论强度 | 编造工具返回、把文件名直接当作已确认攻击、自动判恶意 |
| 域外负向（case6、case10） | 不调用 WebShell 专属知识；不增加 WebShell 事实 | 写入 WebShell 植入、持久化、最终载荷或最终目标 |

每次 Agent 复验至少记录：最终提交 SHA、命令、退出码、报告文件、工具调用、命中条目、trace/run ID 和逐项判定。

## 5. 已有执行证据（历史观察，基线并非当前判据）

| 日期 | 范围 | 证据状态 | 结论 |
|---|---|---|---|
| 2026-09-03 | case1、case2 | 成员回执；基线为旧提交 `42a51ed`，原始报告未进入 PR | 只能作为历史观察，待最终提交复验 |
| 2026-09-03 | case6 | 回执显示调用了 WebShell 知识，并在无输入证据时补出 WebShell 最终载荷/持久化 | 失败 |
| 2026-09-04 | case1、case2、case6 重跑 | PR #40 评论回执称退出码为 0、报告已另存；case6 仅记录“知识调用/命中”，未提供可检查报告 | 进程完成已回执，但 case6 行为验收不能据此判通过 |

> 注：上述为 `knowledge-test-cases/` 旧版 case1-6 的历史观察。旧版已废弃，案例输入迁至 `tests/fixtures/gatekeeper_cases/case1-10.json`；最终验收以新判据（`judgments/caseN.expected.json`）与最新 Commit 复验为准。

## 6. 验收清单

- [x] 门禁/信号/判据/评测汇总/知识工具相关自动化测试通过（2026-09-06，146 passed）。
- [x] 评测汇总 Schema 与最小 fixture 已冻结并加入结构守护测试。
- [x] 闫昱硕 10 份正式判据与一致性守护测试已加入。
- [ ] 新案例（case1-10）在最终提交上完成 Agent 级复验，知识引用与事件证据分开。
- [ ] case6/case10 在最终提交上完成负向复验，未调用 WebShell 知识且未新增 WebShell 事实。
- [ ] Agent 报告、运行元数据和回执保存到团队指定受控位置，仓库只保留判据和结论索引。
- [ ] 不把 Mock/synthetic 成功写成真实 MCP/XDR 联调完成。

## 7. 当前结论

代码层已具备唯一知识源、检索入口、全模式注册、门禁信号分级和自动化边界测试。闫昱硕已在 `judgments/` 收口三档证据规则与 10 份正式判据，并与陈敏信号合同做了一致性 Review。Agent 报告层仍有负向案例（case6/case10）证据缺口待复验，不能因命令退出码为 0 而宣称全部验收通过。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-05 | PR #41 重写测试说明，区分自动化测试、成员回执和 Agent 报告证据 |
| 2026-09-06 | 冻结评测汇总 Schema，新增最小 fixture 与结构守护测试 |
| 2026-09-06 | 废弃 `knowledge-test-cases/` 旧版 case1-6，案例输入迁至 `tests/fixtures/gatekeeper_cases/case1-10.json`；新增闫昱硕判据守护测试 |
