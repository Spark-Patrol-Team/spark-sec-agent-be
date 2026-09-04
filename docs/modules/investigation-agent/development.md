# 深度调查 Agent 模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 深度调查 Agent（`sec_agent.deep_agent` 子智能体） |
| 负责人 | 杨景凡（T0826-03 复验与文档） |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 / 真实平台 / Mock / fallback（各能力实际范围见第 7 节边界表） |
| 关联任务/需求 | T0826-03；PR #13 |
| 关联正式交付章节 | 同 `design.md`（风险研判设计的调查延伸，章节编号待对齐） |
| 对应PR或Commit | PR #13；`383fec7`；`3c49db2`；本次 T0826-03 提交 |
| 适用代码版本 | `main` @ `2ef29a8`（本次提交后更新为最新） |
| 最后更新时间 | 2026-08-26 |

## 1. 当前实现摘要

### 1.1 已实现

- `sec_agent.deep_agent` 完整调查闭环（ReAct 风格，LLM 驱动），接收 `SecurityEventInput` 输出 `InvestigationReport`（`agent.py` / `models.py`）。
- 统一工具层：`Tool` 抽象 + `ToolRegistry`（注册/别名/调用兜底），`tools/base.py`。
- Mock 工具 6 个（`tools/mock.py`，WebShell 主场景人工构造数据）。
- 深信服 MCP 客户端（`tools/mcp_client.py`，JSON-RPC over HTTP，兼容 SSE；5 服务 19 工具，地址走 gitignore 本地配置）。
- MCP 空结果识别：dbproxy 系列工具返回 `{"code":0,"msg":"","data":[]}` 时，`MCPTool.call` 判定为 `partial`（「查询成功但无数据」），与 `success`（有数据）/ `failed`（业务错误 `code!=0` 或异常）区分，供 Agent 按「数据为空」触发停止条件而非静默成功。
- 知识包检索工具 `knowledge_query`（`tools/knowledge.py` + `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` 权威版），关键词匹配返回条目 + `evidence_refs`；CLI 与主链 bridge 均已注册。
- 主链集成：`auto` / `deep_agent` 后端经 `services/deep_agent_bridge.py` 桥接；`tool_mock` 后端走内部子链。
- CLI 入口 `main.py`（`--event` / `-o` 时间戳 / `--list-tools`）、API 可视化配置 `config_gui.py`。

### 1.2 未实现或未复验

- **FastGPT 目标路线**（调查逻辑迁移 FastGPT 编排）：未实现 / 未验证，仅规划。
- 真实平台**数据联调**：深信服 MCP 工具真实连通（dbproxy 等实测调用成功），但本轮查询样例虚构实体返回**合法空集**，真实平台事件数据尚未接入复验。
- 知识包覆盖：问答样本 2（攻击组织）、样本 3（DET0394 细节）无对应章节，属知识包最小集缺口。
- 完整多场景调查（仅 WebShell 主场景有 Mock/知识数据）。

## 2. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/deep_agent/agent.py` | `DeepInvestigationAgent`、`SYSTEM_PROMPT` | 调查闭环、停止条件、人工接管、报告解析与降级 |
| `src/sec_agent/deep_agent/models.py` | `SecurityEventInput` / `InvestigationReport` | 输入事件 / 输出报告模型 |
| `src/sec_agent/deep_agent/config.py` | `Config` / `LLMConfig` / `ToolConfig` / `AgentConfig` | 配置加载（环境变量 > 本地 gitignore 文件 > 默认值） |
| `src/sec_agent/deep_agent/llm.py` | `LLMClient` | OpenAI 兼容 LLM 客户端 |
| `src/sec_agent/deep_agent/main.py` | `build_tools` / `main` | CLI 入口（时间戳输出、`--list-tools`） |
| `src/sec_agent/deep_agent/config_gui.py` | tkinter GUI | LLM API 本地配置可视化界面 |
| `src/sec_agent/deep_agent/tools/base.py` | `Tool` / `ToolResult` / `ToolRegistry` / `ALIAS_MAP` | 工具抽象 + 内部别名层 |
| `src/sec_agent/deep_agent/tools/mock.py` | `build_mock_tools` | 6 个 Mock 兜底工具 |
| `src/sec_agent/deep_agent/tools/knowledge.py` | `build_knowledge_tools` / `KnowledgeQueryTool` / `load_knowledge_entries` | 知识包解析 + `knowledge_query` 检索（`evidence_refs`） |
| `src/sec_agent/deep_agent/tools/mcp_client.py` | `MCPClient` / `MCPTool` / `build_mcp_tools` | 深信服 MCP 客户端 |
| `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` | 《最小 WebShell 知识包》 | 知识包检索源（沈洪旭维护的权威版） |
| `src/sec_agent/services/deep_agent_bridge.py` | `DeepAgentBridge` | 主链桥接（`auto`/`deep_agent` 后端，含 knowledge 工具注册） |
| `src/sec_agent/services/investigation.py` | `DeepInvestigationAgent` | 主链调查服务（三后端分派） |
| `tests/test_investigation_agent.py` | 单元/集成测试 | 16 用例 + 1 集成 |
| `tests/test_knowledge_tool.py` | 知识包检索测试 | 19 用例（含问答样本覆盖） |
| `tests/test_investigation_and_dispatcher_integration.py` | bridge 集成测试 | 5 用例 |

## 3. 依赖与配置

| 名称 | 必需/可选 | 获取方式 | 未配置时行为 |
|---|---|---|---|
| `openai` | 必需 | `pip install openai` | LLM 调用失败 → agent 报错 / 主链回退 |
| `requests` | 必需 | `pip install requests` | MCP/LLM HTTP 失败 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 必需（真实 LLM） | 环境变量或 `llm_config.local.json`（gitignore） | `LLM 未配置` 报错；主链 `auto` 回退内部子链 |
| `LLM_TEMPERATURE` / `LLM_TIMEOUT` | 可选 | 同上 | 默认 `0` / `90` |
| `TOOL_MODE` | 可选 | 环境变量 | 默认 `auto`（Mock + 连上的 MCP 并存） |
| `MCP_URLS` / `mcp_servers.local.json` | 可选 | 环境变量 / gitignore 本地文件 | 未配置/不可达 → 跳过真实 MCP，仅 Mock + 知识包 |
| `MCP_API_KEY` / `MCP_VERIFY_SSL` | 可选 | 环境变量 | 默认空 / 关闭证书校验 |
| `tzdata` | 可选（Windows 必需） | `pip install tzdata` | Windows 主链 import 报 `ZoneInfoNotFoundError`（本机已装，依赖清单待补） |

- 支持的运行环境：Python 3.11+（实测 Windows 11 + Python 3.14.3）；Linux/macOS 理论兼容。
- 敏感配置（LLM key、真实 MCP 地址）只通过环境变量或受控本地文件注入，不在文档、代码和样例中填写真实值。

## 4. 启动与调试

```text
# ① 知识包工具清单（无需 LLM key）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json --list-tools
#   预期：26 个工具（6 Mock + knowledge_query + 19 MCP，MCP 依赖本地配置）

# ② 完整调查（需配置 LLM；-o 自动加时间戳）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

# ③ API 可视化配置 LLM（可选）
PYTHONPATH=src python -m sec_agent.deep_agent.config_gui

# ④ 主链服务（三后端选一）
$env:INVESTIGATION_BACKEND="auto"; $env:PYTHONPATH="src"; python -m uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
```

- 成功判据：`--list-tools` 输出含 `knowledge_query`；完整调查退出码 0 并输出结构化报告（含 `tool_call_records`）。
- 常见失败及排查：
  - `LLM 未配置`：未设 `LLM_*` / 未保存 `llm_config.local.json`。
  - `Invalid function.name 400`：旧版中文工具名问题，已由别名层修复；确认在最新代码。
  - `ZoneInfoNotFoundError: Asia/Shanghai`：Windows 缺 `tzdata`。
  - `ModuleNotFoundError: sec_agent`：未设 `PYTHONPATH=src`。
  - 控制台中文乱码：Windows 控制台编码，不影响运行与报告内容（可用 `PYTHONIOENCODING=utf-8`）。

## 5. 调用与接入方法

### 5.1 调用入口

- CLI：`python -m sec_agent.deep_agent.main --event <json> [-o report.json] [--list-tools]`。
- 主链：`services/investigation.py` `DeepInvestigationAgent.investigate(trace_id, event, triage, run_id)`，经 `deep_agent_bridge.py` 桥接（`auto` / `deep_agent` 后端）。
- HTTP：主链 `POST /runs` → `INVESTIGATING` 阶段触发调查（见 `docs/modules/investigation-agent/test.md` 联调记录）。

### 5.2 最小示例

```text
# 输入事件样例（tests/fixtures/investigation/sample_event.json）
{"event_id":"EVENT-001","event_type":"WebShell","severity":"HIGH","timestamp":"2026-08-22 10:23:15",
 "source_ip":"10.10.10.25","target_ip":"192.168.1.100","alerts":["WebShell通信行为告警"],
 "evidence":["检测到疑似WebShell通信"],"initial_verdict":"疑似真实攻击","confidence":0.72}

# knowledge_query 检索调用（脱敏）
{"keyword":"WebShell处置建议"}
# → status=success；summary 含条目正文 + evidence_refs；data={"entry":"处置建议模板","evidence_refs":["CISA ..."]}
```

### 5.3 上下游接入注意事项

- 主链桥接契约：`DeepInvestigationAgent(config, llm, tools).investigate(event)` 返回 `InvestigationReport`；`_to_domain_report` 把 `verdict`/`confidence`/`tool_call_records`/`disposal_suggestions`/`need_manual_takeover` 等映射为主链领域模型。
- `auto` 后端：bridge 不可用/异常时**回退内部工具子链**（`evidence_lookup` + `xdr_log_query`，无 LLM）；`deep_agent` 后端则置不可用报告。
- `knowledge_query` 返回的 `evidence_refs` 供 Agent 填入报告 `evidence_source`；匹配未命中返回 `failed`，Agent 不得编造条目内容。

## 6. 异常处理与安全控制

- 输入错误：`SecurityEventInput.from_dict` 过滤未知字段；LLM 返回非 JSON → `_extract_json` 兜底 / `_fallback_report`。
- 依赖或工具失败：`ToolRegistry.call` 捕获异常 → `failed`；MCP 连接失败 → 跳过该服务并 `[warn]`，不影响 Mock + 知识包。
- 重复调用与幂等：`_fallback_report` / 工具记录确定性；主链幂等由 `Orchestrator` 的 `idempotency_key` 管理（本模块不涉及）。
- 超时、重试与回滚：LLM `timeout`（默认 90s）；工具调用硬上限 `max_tool_calls=12`（可环境变量 `AGENT_MAX_TOOL_CALLS` 覆盖，防死循环；接近上限时 agent 注入收尾提醒促使 LLM 输出报告，超限仍无报告则降级报告提炼已采证据与知识包引用）；MCP `timeout=20s`；无自动重试（如实记录）。
- 权限、审批与敏感数据：调查只读；处置建议不自动执行；LLM key / MCP 地址不入库、不入文档；`report*.json` 不入库（CLI `-o` 生成在用户目录）。

## 7. 真实平台、Mock与fallback边界

| 能力 | 当前实际实现 | 触发条件 | 不得误写为 |
|---|---|---|---|
| LLM 推理 | **真实调用**（DeepSeek OpenAI 兼容接口，实测通过） | 配置 `LLM_*` 或本地配置 | FastGPT 编排（未实现） |
| 深信服 MCP 工具 | **真实连通**（5 服务 19 工具注册；dbproxy 等实测调用返回） | 配置 `MCP_URLS` / `mcp_servers.local.json` 且网络可达 | 真实平台**数据**已验证（本轮查询样例虚构实体返回空集，待真实数据联调） |
| Mock 工具（6 个） | **本地实现**（人工构造 WebShell 演示数据） | `TOOL_MODE=mock`/`auto` | 真实平台返回 |
| 知识包检索（`knowledge_query`） | **本地实现**（解析沈洪旭权威版 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` 为条目 + `evidence_refs`） | 所有工具模式注册 | FastGPT 知识库 / 真实知识服务 |
| 内部回退子链 | **fallback**（`evidence_lookup` + `xdr_log_query`，无 LLM） | `auto` 后端 bridge 不可用/异常 | 真实 LLM 已运行 |
| FastGPT 目标路线 | 未实现 | — | 已接入 FastGPT |

## 8. 已知限制与待办

| 优先级 | 事项 | 是否影响主链 | 负责人/完成条件 |
|---|---|---|---|
| P1 | Windows 缺 `tzdata` 依赖（建议补入 `pyproject.toml`） | 是（主链 import 即挂） | 补依赖 + 跨平台验证 |
| P1 | 真实平台事件数据联调（dbproxy 空数据问题） | 是（真实场景证据采集） | 真实 XDR 数据接入后复验 |
| P2 | 知识包最小集缺口（攻击组织、DET0394 细节等） | 否 | 扩充知识包章节 |
| P2 | 仅覆盖 WebShell 主场景 | 否 | 扩展场景数据 |
| P2 | 文档与《系统设计说明书》章节编号对齐 | 待确认 | 后续对齐 |

## 9. 运行观测、版本兼容与迁移

- 日志与关键指标位置：`tool_call_records`（报告字段）、`investigation_steps`（报告字段）、CLI 工具清单、主链 `GET /events/{id}/timeline`。
- 健康检查或运行状态判断：主链 `GET /health`；CLI 退出码 0 为成功。
- 兼容的接口/Schema/平台版本：OpenAI 兼容 `chat/completions`；MCP JSON-RPC 2.0 over HTTP（SSE 兼容）；深信服 MCP 函数名以 `ALIAS_MAP` 为契约。
- 升级、迁移或回退注意事项：`ALIAS_MAP` 与深信服侧函数名需同步更新；bridge 双包名兼容已可容忍包位置变化；知识包 md 结构变化需同步 `_ENTRY_SPECS`。

## 10. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-24 | PR #13 | 子智能体落地 `sec_agent.deep_agent` | `test_investigation_agent.py` |
| 2026-08-25 | `383fec7` | bridge 双包名修复 | `test_investigation_and_dispatcher_integration.py` |
| 2026-08-25 | `3c49db2` | `-o` 报告时间戳 | `test_investigation_agent.py` |
| 2026-08-26 | 本次 T0826-03 提交 | 新增 `knowledge_query` 知识包检索工具 + 知识包入库 | `tests/test_knowledge_tool.py`（19 用例） |
| 2026-08-26 | 本次（方案 C 提交） | `max_tool_calls` 8→12（`AGENT_MAX_TOOL_CALLS` 覆盖）；接近上限收尾提醒；`_fallback_report` 提炼已采证据与知识包引用 | `test_investigation_agent.py` 新增 5 用例（合计 47 passed / 1 skipped） |
| 2026-08-27 | 本次 T0827-03 提交 | 知识源统一：`knowledge_query` 改读沈洪旭权威版 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`，删除本地副本 `webshell_min.md`；MCP 空结果识别：dbproxy `{"code":0,"data":[]}` → `partial`（查询成功但无数据） | `test_mcp_client.py` 新增（11 用例）；`test_knowledge_tool.py` 全通过 |
| 2026-08-27 | 本次（打包修复） | 知识包迁入 `sec_agent.deep_agent` 包内 + `[tool.setuptools.package-data]` 随 wheel/sdist 分发，`knowledge.py` 改用 `importlib.resources` 读取；`-o` 时间戳改微秒级 + 存在检测唯一序号 | `test_packaging.py` 新增（4 用例）；`test_investigation_agent.py` 时间戳用例更新 |
| 2026-09-04 | PR #31收口 | 非dbproxy空文本改为`partial`；`isError=true`、`{"error":...}`、输入校验/字段排除/HTTP 4xx或5xx前缀改为`failed`，避免错误文本作为成功证据 | `test_mcp_client.py` 18例 |
