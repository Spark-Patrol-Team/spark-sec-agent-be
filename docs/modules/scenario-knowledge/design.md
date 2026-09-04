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
| 评测输入 | `docs/modules/scenario-knowledge/knowledge-test-cases/` 下 6 个 synthetic 案例 |

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

当前条目覆盖攻击原理、攻击特征速查表、主流管理工具与流量特征、证据检查清单、处置建议模板、停止条件与人工接管规则。

## 5. 安全与证据边界

- 知识命中只说明“找到了相关通用知识”，不说明事件中的对应行为已经发生。
- `evidence_refs` 是知识条目的来源引用，不是本次事件的观测证据。
- 证据不足或工具失败时，Agent 应降低结论强度并列出缺口，必要时建议人工接管。
- 6 个案例均为公开材料改编或人工构造的 synthetic 输入，不是 XDR 原始响应，也不是运行 A/运行 B。
- case6 是纯非 WebShell 负向对照；当前 WebShell 专属知识不应被用于补写 WebShell 植入、持久化或最终载荷。
- 案例来源能支持和不能支持的具体主张以 `knowledge-test-cases/来源矩阵.md` 为准。

## 6. 关键设计决策

1. **单一正文**：运行时只读取包内 `webshell-knowledge.md`，避免文档副本漂移。
2. **ASCII 工具名**：OpenAI 兼容函数名不允许点号，因此使用 `knowledge_query`，语义对应需求中的 `knowledge.query`。
3. **确定性检索**：当前采用可测试的关键词规则，不引入向量库、RAG 服务或 FastGPT 依赖。
4. **显式失败**：未知主题返回未命中，不用相近条目强行回答。
5. **知识与证据分层**：知识负责“该查什么”，事件与工具输出负责“实际发生了什么”。

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
