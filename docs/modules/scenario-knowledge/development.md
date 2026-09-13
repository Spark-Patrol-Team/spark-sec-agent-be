# 场景知识模块开发说明

## 1. 代码与资产位置

| 内容 | 路径 |
|---|---|
| 工具实现 | `src/sec_agent/deep_agent/tools/knowledge.py` |
| 唯一知识正文 | `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` |
| 门禁实现 | `src/sec_agent/services/gatekeeper.py` |
| 工具注册 | `src/sec_agent/deep_agent/main.py::build_tools`与`src/sec_agent/services/deep_agent_bridge.py::_build_tools` |
| 包数据声明 | `pyproject.toml` 的 `[tool.setuptools.package-data]` |
| 工具单元测试 | `tests/test_knowledge_tool.py` |
| 案例输入边界测试 | `tests/test_knowledge_case_inputs.py` |
| 评测案例与来源说明 | `docs/modules/scenario-knowledge/knowledge-test-cases/` |

不要在 `docs/` 下再复制一份 WebShell 知识正文。需要更新知识时，只修改唯一运行时文件，并同步补充测试。

## 2. 实现结构

当前运行时使用`parse_knowledge_cards()`通过`importlib.resources`读取包内Markdown，并按`## 知识ID：WSK-*`解析15张`KnowledgeCard`。每张卡至少包含：

- `knowledge_id`与`topic`；
- `applicability`与`required_evidence`；
- `investigation_steps`、`false_positives`和`prohibited_inference`；
- `source_urls`、`source_levels`与`related_cases`。

`match_knowledge_card()`按知识ID精确匹配、受控别名、主题精确匹配和主题包含匹配依次查找。无确定命中时返回`None`。禁止恢复旧`KnowledgeEntry/_ENTRY_SPECS/load_knowledge_entries/match_keyword`并行解析链。

`KnowledgeQueryTool.call()` 的调用示例：

```python
result = KnowledgeQueryTool(gate_decision="in_scope").call({"keyword": "WebShell处置建议"})
```

`in_scope`命中返回`success`和结构化知识卡；`weak_signal`返回`partial`但不返回确认性知识。正式CLI/bridge对`out_of_scope`和门禁缺失不注册工具；只有直接实例化工具的防御性路径才返回对应`failed`。调用方不得把未命中、门禁错误或空结果改写为确定性知识。

## 3. 接入方式

CLI和主链bridge都必须先从事件计算三档门禁，再把`gate_decision`传给`build_knowledge_tools()`。知识文件不依赖MCP可用性，但工具并非无条件存在：只有`in_scope/weak_signal`才注册；`out_of_scope`、`KNOWLEDGE_MODE=off`、门禁缺失或门禁异常时均不注册。工具内部仍保留域外和缺门禁拒绝，作为误注册时的第二道防线。

CLI通过`normalize_event_payload()`同时兼容case1—6的扁平事件结构和case7—10的`input_event`包裹结构。禁止仅在测试辅助函数中拆包，否则正式CLI会把包裹对象解析为空事件并得到错误门禁结果。

工具名固定为 `knowledge_query`。不要改成包含点号的 `knowledge.query`，因为 OpenAI 兼容函数名要求匹配 `^[a-zA-Z0-9_-]+$`。

可通过以下命令检查注册结果：

```powershell
$env:PYTHONPATH = "src"
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case9.json --list-tools
```

## 4. 本地验证

在仓库根目录执行：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_knowledge_tool -v
python -m unittest tests.test_knowledge_case_inputs -v
```

若本机 LLM 配置可用，可运行两个正向案例和 case6 负向对照：

```powershell
$env:PYTHONPATH = "src"
$env:TOOL_MODE = "mock"
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case1.json -o reports/case1.json
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case2.json -o reports/case2.json
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case6.json -o reports/case6.json
```

`TOOL_MODE=mock` 只验证本地代码契约和 Agent 消费，不代表真实 MCP 或真实 XDR 已打通。`report*.json` 是本地运行产物，已被 `.gitignore` 排除；正式验收时应把报告及运行元数据交到团队指定的受控位置，而不是提交到仓库。

## 5. 知识与案例维护

修改知识正文或关键词时：

1. 确认新增内容有可追溯来源，并区分一手来源、二手来源和 synthetic 构造。
2. 只更新唯一运行时知识正文。
3. 为新增条目、关键词、未命中行为和 `evidence_refs` 增加测试。
4. 若影响案例，更新 `来源矩阵.md` 中“可支持/不可支持”的主张。
5. 对正向、证据不足和纯负向案例分别复验，不能只看进程退出码。

## 6. 异常与安全控制

- 知识文件缺失或打包遗漏应在启动/构建测试中暴露，不能静默切换到文档副本。
- 空查询和未知主题返回失败；调用方应记录知识缺口。
- `evidence_refs` 只能作为知识来源，不能冒充事件证据。
- Agent 报告不得超出输入、真实工具输出和来源矩阵所允许的事实范围。
- case6 不含 WebShell 证据；若调用 WebShell 知识或新增 WebShell 结论，应判为失败。
- case10是SSH暴力破解域外负向案例；不得仅凭一般外连或登录后可能性套用WebShell植入/C2知识。
- 门禁`None`、非法值或审计异常时必须禁用知识工具；工具对象即使被无门禁创建，也返回`missing_knowledge_gate_decision`。

## 7. 已知限制

- 当前是关键词检索，不支持向量检索、模糊语义匹配和跨场景知识编排。
- 当前知识正文只覆盖 WebShell；其他场景需要独立知识资产和测试后再接入。
- 单元测试不能代替对最终 LLM 报告的人工/规则复核。
- 当前案例不是实际 XDR 原始报文，不能用来宣称真实平台联调完成。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-04 | PR #37 合入评测案例；PR #40 校正案例来源与边界 |
| 2026-09-05 | PR #41 依据当前运行时实现重写开发说明，并明确维护与验收方法 |
| 2026-09-13 | 最终收口候选实现CLI/bridge先门禁后注册、知识工具缺门禁二次拒绝、通用冲突提示和否定/域外语义测试；`pyproject.toml`加入Windows时区依赖 |
| 2026-09-13 | 清理旧`KnowledgeEntry`解析实现和旧测试，正式运行与测试统一使用15张`KnowledgeCard`；同步`out_of_scope`正式路径不注册工具的接口说明 |
