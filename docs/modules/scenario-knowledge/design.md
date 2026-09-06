# 场景知识模块设计

## 1. 模块职责

场景知识模块为深度调查 Agent 提供本地 WebShell 知识检索。它把唯一知识正文解析为可查询条目，返回正文和来源引用，供 Agent 形成调查方向、证据检查项和处置建议。

本模块提供调查参考，不替代事件证据，也不把知识模板中的通用描述当作当前事件已经发生的事实。

## 2. 当前实现

| 项目 | 当前状态 |
|---|---|
| 唯一运行时知识正文 | `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` |
| 查询实现 | `src/sec_agent/deep_agent/tools/knowledge.py` |
| LLM 可见工具名 | `knowledge_query` |
| 工具注册 | `src/sec_agent/deep_agent/main.py::build_tools`，在 `mock`、`mcp`、`auto` 模式下均注册 |
| 随包分发 | `pyproject.toml` 将 `knowledge/*.md` 声明为 package data |
| 评测输入 | `tests/fixtures/gatekeeper_cases/case1.json ~ case10.json`（陈敏 PR#43 的权威事件信号合同） |
| 评测汇总 Schema | `tests/fixtures/evaluation/knowledge_evaluation_summary.schema.json` |

文档目录不保存第二份运行时知识正文。PR #8 是历史知识资产来源之一，其有价值内容已按当前结构吸收，不直接形成并行入口。

## 3. 输入与输出

输入为一个非空字符串参数：

```json
{"keyword": "WebShell证据检查清单"}
```

命中时返回：

- `status=success`；
- `summary`：条目正文和 `evidence_refs`；
- `data.entry`：命中的条目名；
- `data.evidence_refs`：该条目的来源引用。

未命中或输入为空时返回 `status=failed`，明确说明知识库无匹配，不生成兜底事实。

## 4. 核心流程

1. `build_tools` 在工具注册表中注册 `knowledge_query`。
2. 工具通过 `importlib.resources` 读取随包分发的唯一知识正文。
3. 加载器按 Markdown 标题解析条目。
4. 查询器对预设关键词执行确定性匹配，返回得分最高的条目。
5. Agent 可把返回内容用作调查提示，但最终结论仍须受输入事件和实际工具证据约束。
6. Agent 评测完成后，逐案例结果按冻结 Schema 汇总，人工 Review 结论只写入 `human_review` 栏，不反向修改原始案例输入。

当前条目覆盖攻击原理、攻击特征速查表、主流管理工具与流量特征、证据检查清单、处置建议模板、停止条件与人工接管规则。

## 5. 安全与证据边界

- 知识命中只说明“找到了相关通用知识”，不说明事件中的对应行为已经发生。
- `evidence_refs` 是知识条目的来源引用，不是本次事件的观测证据。
- 证据不足或工具失败时，Agent 应降低结论强度并列出缺口，必要时建议人工接管。
- 本批 case1-10 均为公开材料改编或人工构造的 synthetic 输入，不是 XDR 原始响应，也不是运行 A/运行 B。
- case6 是纯非 WebShell 负向对照；当前 WebShell 专属知识不应被用于补写 WebShell 植入、持久化或最终载荷。
- 案例来源能支持和不能支持的具体主张以 `judgments/来源主张边界review.md` 为准。

## 6. 关键设计决策

1. **单一正文**：运行时只读取包内 `webshell-knowledge.md`，避免文档副本漂移。
2. **ASCII 工具名**：OpenAI 兼容函数名不允许点号，因此使用 `knowledge_query`，语义对应需求中的 `knowledge.query`。
3. **确定性检索**：当前采用可测试的关键词规则，不引入向量库、RAG 服务或 FastGPT 依赖。
4. **显式失败**：未知主题返回未命中，不用相近条目强行回答。
5. **知识与证据分层**：知识负责“该查什么”，事件与工具输出负责“实际发生了什么”。
6. **汇总 Schema 冻结**：评测输出统一使用 `knowledge_evaluation_summary.schema.json`，避免不同成员用自由表格记录导致字段漂移。

## 7. 上下游关系

- 上游：`SecurityEventInput`、Agent 调查计划以及用户/模型生成的查询词。
- 本模块：加载、匹配并返回知识条目和来源引用。
- 下游：`DeepInvestigationAgent` 的证据检查、研判说明、处置建议和人工接管判断。

## 8. 当前限制

- 目前仅覆盖 WebShell 场景，供应链、插件异常等主题应返回知识缺口。
- 关键词规则不具备语义召回能力；同义表达需要显式补充并增加测试。
- 自动化测试可验证加载、匹配、注册和案例输入边界，但不能单独证明 LLM 报告没有扩写事实。
- case6 的最终报告仍需在受控位置复核后，才能确认 Agent 级负向约束通过。

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-04 | PR #37 合入 6 个 synthetic 案例及初版边界记录 |
| 2026-09-04 | PR #40 校正来源矩阵、案例判据和自动化输入边界测试 |
| 2026-09-05 | PR #41 按当前 `main` 的真实实现重写设计说明，删除旧 PR #8 状态残留 |
| 2026-09-06 | 冻结评测汇总 Schema 和最小 fixture，补充人工 Review 栏 |
| 2026-09-06 | 闫昱硕收口三档证据规则与 10 份正式判据；废弃 `knowledge-test-cases/` 旧版 case1-6，案例输入迁至 `tests/fixtures/gatekeeper_cases/case1-10.json` |

## 10. case1-10 正式信号强度总表与期望集合

> 由闫昱硕在 T0905-03 收口，基于陈敏 `PR#43` 的 `tests/fixtures/gatekeeper_cases/caseN.json` 与 `src/sec_agent/services/gatekeeper.py` 的 `SignalStrength`。期望集合与 `tests/test_gatekeeper_case1_10.py::TestTask6HandoverAssertions::test_yanyushuo_signal_strength_and_verdict` 对齐。

| case | case_id | 事件类型 | 总体强度（期望） | 允许偏离集合 | 三档门禁 | 人工接管 | 备注 |
|---|---|---|---|---|---|---|---|
| case1 | TC-KNOWLEDGE-001 | WebShell | `IN_SCOPE_WEAK` | WEAK, CONFIRMED, MIXED, INDETERMINATE | `weak_signal` | 否 | IIS UpdateChecker.aspx，弱信号，不得确认冰蝎 |
| case2 | TC-KNOWLEDGE-002 | WebShell | `IN_SCOPE_CONFIRMED` | CONFIRMED, MIXED | `in_scope` | 是 | ⚠️ 输入与来源矩阵冲突（Godzilla/ViewState/Wingtb.sys），判据不得据知识定家族/持久化 |
| case3 | TC-KNOWLEDGE-003 | WebShell | `IN_SCOPE_WEAK` | WEAK, CONFIRMED, MIXED, INDETERMINATE | `weak_signal` | 是 | ⚠️ 门禁可能因 RSA 强关键词判 CONFIRMED，判据按来源边界保守收口 |
| case4 | TC-KNOWLEDGE-004 | WebShell | `IN_SCOPE_WEAK` | WEAK, INDETERMINATE | `weak_signal` | 是 | 单条告警缺上下文 |
| case5 | TC-KNOWLEDGE-005 | WebShell | `IN_SCOPE_WEAK` | WEAK, INDETERMINATE | `weak_signal` | 是 | 关键工具调用失败 |
| case6 | TC-KNOWLEDGE-006 | WordPress_Compromise | `OUT_OF_SCOPE` | OUT_OF_SCOPE | `out_of_scope` | 否 | 供应链/插件，纯非 WebShell 负向 |
| case7 | TC-KNOWLEDGE-007 | WebShell | `MIXED` | MIXED, BENIGN_LIKE, WEAK | `weak_signal` | 否 | 合法上传（multipart/image/png/Base64 参数），保留良性可能 |
| case8 | TC-KNOWLEDGE-008 | WebShell | `IN_SCOPE_WEAK` | IN_SCOPE_WEAK | `weak_signal` | 否 | 仅文件名 shell.php，无访问/执行记录 |
| case9 | TC-KNOWLEDGE-009 | WebShell | `IN_SCOPE_CONFIRMED` | IN_SCOPE_CONFIRMED | `in_scope` | 是 | 异常POST→文件修改→w3wp 拉起 cmd→HTTP200 回显，确认命令执行 |
| case10 | TC-KNOWLEDGE-010 | WebShell | `OUT_OF_SCOPE` | OUT_OF_SCOPE | `out_of_scope` | 否 | ⚠️ 输入 event_type 误标 WebShell，实际为 SSH 暴力破解（需陈敏修正） |

### 期望口径说明

- `expected_scope`（三档）是判据收口口径，可能与门禁 `overall_strength` 有细微拆分（如 case3 门禁给 CONFIRMED，判据按来源边界取 `weak_signal`）。
- `weak_signal` 案例只允许返回检查清单/误报条件/证据缺口，禁止确认性攻击结论与无条件高风险处置。
- `in_scope`（case2/case9）允许报告输入中已观察到的强证据为事实，但禁止把知识/启发线索扩写成输入中不存在的事实（横向、窃取、持久化、家族归属、初始路径）。
- `out_of_scope`（case6/case10）拒绝 WebShell 专属知识、记录 `knowledge_scope_mismatch`，禁止补写 WebShell 攻击链。
- 判据正文见 `judgments/caseN.expected.json`；单独保存，不写入 `caseN.json`。
