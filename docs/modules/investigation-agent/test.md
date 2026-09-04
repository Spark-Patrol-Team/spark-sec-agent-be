# 深度调查 Agent 模块测试说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 深度调查 Agent（`sec_agent.deep_agent` 子智能体） |
| 负责人 | 杨景凡（T0826-03 复验与文档） |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 / 真实平台 / Mock / fallback（各能力实际范围见 `development.md` 第 7 节边界表与本文第 6 节复验信息） |
| 复验基线 | `main` @ `2ef29a8`（本次提交后更新为最新） |
| 复验时间 | 2026-08-25（main + Mock）、2026-08-26（真实 LLM + 前端接口联调 + 知识包检索） |
| 复验环境 | Windows 11 + Python 3.14.3；LLM：DeepSeek OpenAI 兼容接口（key 走 gitignore 本地文件）；深信服 MCP 5 服务（地址走 gitignore 本地文件） |
| 对应PR或Commit | PR #13；`383fec7`；`3c49db2`；本次 T0826-03 提交 |
| 最后更新时间 | 2026-08-26 |

## 1. 测试目标与非目标

### 1.1 目标

- 验证 `sec_agent.deep_agent` 真实加载：主链 bridge（`auto`/`deep_agent` 后端）能加载真实子智能体模块，而非错误地走内部回退子链。
- 验证调查闭环：工具调用留痕、结构化报告生成、证据不足时人工接管（`need_manual_takeover` → 主链 `HUMAN_REQUIRED`）。
- 验证知识包检索工具 `knowledge_query`：关键词命中条目、返回 `evidence_refs`、覆盖问答样本、注册进 CLI 与 bridge 工具集。
- 验证 Mock 工具稳定复验：不依赖外部服务的单元/集成测试稳定通过。

### 1.2 非目标

- 不承诺真实平台**数据**已验证：深信服 MCP 工具真实连通（本轮 dbproxy 等实测调用返回 `code:0`），但查询的样例虚构实体返回合法空集，真实事件数据联调待平台侧。
- 不验证 FastGPT 目标路线（未实现）。
- 不验证多场景（仅 WebShell 主场景有 Mock/知识数据）。

## 2. 测试范围

- 数据模型：`SecurityEventInput` / `InvestigationReport` 序列化与往返。
- Mock 工具：命中 / 未命中 / 未知工具 / 注册数量。
- 工具名别名层：中文 MCP 工具名 → ASCII 内部别名，解析还原。
- 知识包检索：条目解析、关键词打分、`evidence_refs`、问答样本覆盖、注册唯一性。
- Agent 辅助逻辑：JSON 提取（含代码块围栏、噪声）、降级报告。
- 集成测试：完整 WebShell 调查闭环（需 LLM key，未配置时跳过）；bridge 加载真实模块回归。

## 3. 测试环境与依赖

| 项 | 值 |
|---|---|
| OS | Windows 11（Home China 10.0.26200） |
| Python | 3.14.3 |
| 依赖 | `openai`、`requests`、`tzdata`（Windows 必需，已装） |
| LLM | DeepSeek OpenAI 兼容（`llm_config.local.json`，gitignore） |
| MCP | 深信服 5 服务（`mcp_servers.local.json`，gitignore） |
| 数据 | 全为人工构造样例（`sample_event.json` / `fixed_sample.py` / `mock.py` / 知识包），无真实事件数据 |

## 4. 测试数据说明

| 数据 | 来源 | 性质 |
|---|---|---|
| `tests/fixtures/investigation/sample_event.json` | 人工构造 | WebShell 固定样例（Mock），非真实平台数据 |
| `src/sec_agent/platforms/fixed_sample.py`（`webshell-001`） | 人工构造 | 主链样例：src_ip=10.10.2.15 / dst_ip=172.16.8.21 / 告警 xdr-alert-001/002 |
| `src/sec_agent/deep_agent/tools/mock.py` 内置表 | 人工构造 | 仅覆盖 192.168.1.100（OA 服务器）；未知 IP 按设计返回 failed/数据不可得 |
| `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md` | 人工构造（知识包最小集，沈洪旭维护的权威版） | 攻击原理 / 特征速查 / 工具流量 / 检查清单 / 处置建议 / 人工接管 |
| 《问答样本示例_v1.md》 | 人工构造 | 5 题评测样本，用于知识包检索覆盖验证 |

## 5. 测试用例

### 5.1 数据模型与 Mock 工具（`tests/test_investigation_agent.py`）

| 用例 | 验证点 |
|------|--------|
| `test_event_roundtrip` | 事件模型 `from_dict` / `to_dict` 往返一致 |
| `test_report_serializable` | 报告可 JSON 序列化 |
| `test_asset_query_hit` | `query_asset` 命中 OA 服务器 |
| `test_asset_query_miss` | 未知 IP 返回 `failed`（数据不可得） |
| `test_unknown_tool` | 未知工具返回 `failed` |
| `test_mock_tools_registered` | 注册至少 6 个 Mock 工具 |
| `test_extract_json_plain` / `_fenced` / `_with_noise` | JSON 提取（纯 / 代码块围栏 / 带噪声） |
| `test_safe_json_loads` | 非法 JSON 兜底为空 dict |
| `test_fallback_report` | 证据不足 → 人工接管 |
| `test_ascii_tool_keeps_name` | ASCII 工具名别名＝真实名 |
| `test_chinese_tool_aliased_and_resolved` | 中文工具名映射内部别名，可解析还原 |
| `test_unknown_tool_still_fails` | 未收录中文名解析失败（不静默放行） |
| `test_alias_map_consistency` | `ALIAS_MAP` 值均 ASCII 且对应真实名 |
| `test_mock_schemas_ascii_unique` | Mock schema 全 ASCII 且不重复 |
| `test_web_shell_full_run` | 完整 WebShell 调查（需 LLM key，未配置时跳过） |
| `test_fallback_report_extracts_knowledge_refs` | 降级报告提炼已采证据：knowledge_query 的 `evidence_refs` → evidence_source、成功工具返回 → key_evidence（方案 C） |
| `test_default_max_tool_calls` 等 4 例 | AgentConfig 步数上限：默认 12 / 步数 5 / `AGENT_MAX_TOOL_CALLS` 覆盖 / 非法值回退（方案 C） |

### 5.2 知识包检索工具（`tests/test_knowledge_tool.py`，2026-08-26 新增）

| 用例 | 验证点 |
|------|--------|
| `test_entries_loaded` | 知识包解析出核心条目（攻击原理 / 特征速查 / 工具流量 / 检查清单 / 处置建议） |
| `test_attack_principle_content_not_empty` | 条目正文非空 |
| `test_match_attack_principle` 等 6 例 | 关键词命中：攻击原理 / 处置建议 / 工具流量 / 检查清单 / 人工接管 / 无关词未命中 |
| `test_schema_ascii_and_name` | schema 名 `knowledge_query` 符合 `^[a-zA-Z0-9_-]+$` |
| `test_hit_returns_evidence_refs` | 命中返回 `evidence_refs`，summary 同步携带供 LLM 阅读 |
| `test_attack_principle_evidence_ref` | 攻击原理条目含 T1505.003 引用 |
| `test_miss_returns_failed` | 无关关键词返回 `failed` |
| `test_registered_in_registry` | 注册进 `ToolRegistry`，schema 名唯一 |
| `test_sample1..5` | 问答样本覆盖：样本 1/3/4/5 命中对应条目；样本 2（攻击组织）为知识缺口（如实标记） |

### 5.3 MCP 客户端契约（`tests/test_mcp_client.py`，2026-08-27 新增，任务二）

| 用例 | 验证点 |
|------|--------|
| `TestExtractText` 3 例 | `_extract_text` 兼容 content 列表 / structuredContent / 纯字符串 |
| `TestDbproxyContract` 6 例 | dbproxy 契约：空数据→`partial`、非空→`success`、`code!=0`→`failed`、`code="0"` 字符串及空error字段兼容 |
| `TestNonDbproxyTool` 7 例 | 空文本→`partial`；`isError`、error JSON和已知错误前缀→`failed`；正常研判文本仍为`success` |
| `TestMCPToolEndToEnd` 2 例 | `MCPTool.call` 端到端：空结果 `partial`、有数据 `success`，供 Agent 消费 |

### 5.4 bridge 集成（`tests/test_investigation_and_dispatcher_integration.py`）

| 用例 | 验证点 |
|------|--------|
| `test_bridge_loads_real_deep_agent_modules` | bridge 能从 `sec_agent.deep_agent` 加载真实模块（修复前必挂） |
| 其余 4 例 | 后端分派 / 领域模型互转 / 报告映射 |

## 6. 复验信息（真实执行路径）

本轮复验确认的实际运行路径（按实际情况记录，不夸大）：

| 复验项 | 2026-08-25（main + Mock） | 2026-08-26（真实 LLM + 前端联调） | 2026-08-26（知识包） |
|---|---|---|---|
| 真实加载 `sec_agent.deep_agent` | ✅ 是（bridge 加载真实模块） | ✅ 是（`auto` 后端） | — |
| 实际调用 LLM | ✅ 是（配置 key） | ✅ 是 | — |
| 内部 fallback 发生 | ❌ 否 | ❌ 否（工具名全为 deep_agent 工具集） | — |
| 工具调用 | 7 次（6 Mock 工具） | 8 次（4 Mock failed + 4 dbproxy MCP 空） | 19 例检索测试 |
| 结构化报告 | ✅ 完整 | ✅ 完整（`need_manual_takeover=true`） | — |
| 结束状态 | 报告含人工接管标记 | 主链停在 `HUMAN_REQUIRED` | — |

判定「真实 LLM 路径 / 内部回退子链」的依据：工具名（真实路径为 `query_asset`/`query_alerts`/`dbproxy_*` 等 deep_agent 工具集，内部子链为 `evidence_lookup`/`xdr_log_query`）与 `tool_results` 数量（8 次 vs 2 次）。

### 6.1 2026-08-27 固定样例完整调查（知识源统一 + partial 契约后）

用 `tests/fixtures/investigation/sample_event.json` 固定样例跑通完整结构化调查（报告 `report_20260827_214442.json`，本次提交后生成），证明「工具结果真正影响证据/结论」，而非仅证明函数可导入：

| 复验项 | 结果 |
|---|---|
| 调查 Agent 正常执行 | ✅ 8 次工具调用（6 Mock + `knowledge_query` + `query_asset` 失败 1 次），产出完整结构化报告 |
| 工具结果进入调查过程 | ✅ `tool_call_records` 完整留痕：工具名 / 输入 / 输出 / 状态，逐条可审计 |
| 知识源切换生效 | ✅ `knowledge_query`（关键词「WebShell证据检查清单」）返回正文来自沈洪旭权威版 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`（5 项检查清单 + `[引用来源：NSA/CISA 联合报告；CISA Eliminate Web Shells (CM0106)]`） |
| 工具返回影响证据来源 | ✅ `evidence_refs`（NSA/CISA、CM0106）结构化进入 `tool_call_records`，并同步进入报告的 `evidence_source` |
| 工具返回影响处置建议 | ✅ `disposal_suggestions` 8 条，由知识包处置模板（CISA CM0106 隔离→保全→删除→改密→根因→恢复→加固）驱动 |
| 工具返回影响结论与置信度 | ✅ 结论判定「真实 WebShell 攻击」，`confidence=0.88`（随 Mock 资产/告警/漏洞证据上调） |
| 未内部 fallback | ✅ 工具名全为 deep_agent 工具集（非 `evidence_lookup`/`xdr_log_query`） |

本轮报告的 `report_*.json` 不入库（gitignore），上述结论为对报告字段的实际核对。

## 7. 执行方式（真实执行命令）

```bash
# 单元 + 集成测试（不依赖 LLM key 的部分稳定通过）
PYTHONPATH=src python -m pytest tests/test_knowledge_tool.py tests/test_investigation_agent.py tests/test_investigation_and_dispatcher_integration.py -q
#   预期：47 passed / 1 skipped（1 项为需 LLM key 的集成用例）

# 或无需 pytest
PYTHONPATH=src python -m unittest tests.test_investigation_agent -v
PYTHONPATH=src python -m unittest tests.test_knowledge_tool -v

# 工具清单（无需 LLM key；MCP 依赖本地配置）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json --list-tools
#   预期：26 个工具（6 Mock + knowledge_query + 19 MCP）

# 完整调查（需配置 LLM key；-o 自动加时间戳）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

# 主链服务 + 前端接口联调（PowerShell）
$env:INVESTIGATION_BACKEND="auto"; $env:PYTHONPATH="src"; python -m uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
# ① POST /runs  body {"source":"fixed_sample","sample_id":"webshell-001"}
# ② GET /events/{id}/timeline 、 GET /events/{id} 、 GET /metrics
```

## 8. 结果汇总

- 单元测试（`test_investigation_agent.py`）16 项通过 / 1 项跳过（合计 17，均不依赖 LLM）。
- bridge 集成测试（`test_investigation_and_dispatcher_integration.py`）5 项通过（含真实模块加载回归）。
- 知识包检索（`test_knowledge_tool.py`）19 项全部通过；`knowledge_query` 已注册（CLI 与主链 bridge，6 mock + 1 knowledge + 19 mcp = 26）；问答样本 5 题中 4 题命中，样本 2（攻击组织）如实标记为知识缺口。
- 完整调查（真实 LLM，独立运行）：7 次 Mock 工具调用、完整结构化报告、未内部 fallback。
- 主链实测（`auto` 后端，真实 LLM）：8 次工具调用（4 Mock failed + 4 dbproxy MCP 空）→ `need_manual_takeover=true` → 停在 `HUMAN_REQUIRED`，不自动处置；未发生内部 fallback。
- 主链实测（`tool_mock` 后端，内部子链）：2 次工具调用（`evidence_lookup` + `xdr_log_query`）→ 处置方案 → `APPROVAL_REQUIRED` → 审批 → `EXECUTING` → `VERIFYING` → `COMPLETED`；`GET /events/{id}/timeline` 9 步完整、`GET /metrics` 完成计数 +1。

## 9. 验收结论

| 验收项（T0826-03） | 结果 |
|---|---|
| 最新 main 能真实加载 `sec_agent.deep_agent` | ✅ 实测通过（bridge 加载真实模块 + 主链 `auto` 后端真实运行） |
| Mock 工具稳定复验 | ✅ 16 passed / 1 skipped（不依赖 LLM），主链 `tool_mock` 后端全链 COMPLETED |
| 实际运行路径确认 | ✅ 真实加载 PR #13 Agent + **实际调用 LLM** + **未发生内部 fallback**（按工具名与调用次数判据） |
| 文档按模板同步三份 | ✅ `design.md` / `development.md` / `test.md`（本文件）均按 0-10 节模板完善，能力性质边界区分见 `development.md` 第 7 节 |
| 知识包纳入 git 提交 | ✅ 统一读沈洪旭权威版 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`，删除本地副本 `webshell_min.md`，`knowledge_query` 随本次提交 |

## 10. 已知问题与上游分析

### 10.1 已知问题汇总（2026-08-26，按「问题（所属环节）：具体原因」）

1. **Mock 工具 4 次全部「数据不可得」（深度调查环节 → LLM 调 Mock 工具）**：LLM 从样例事件抽出 172.16.8.21 / 10.10.2.15 去查资产/告警/漏洞，但 `mock.py` 内置表只覆盖 192.168.1.100（OA 服务器）→ `.get(ip)` 返回空 → 按设计返回 failed/数据不可得。属工具内置预期边界，非 bug。
2. **dbproxy MCP 4 次全部返回空数据 `data:[]`（深度调查环节 → LLM 调真实 MCP 工具）**：连接、鉴权、JSON-RPC 全部成功（`code:0`），空的是结果集——查询的 IP 172.16.8.21、告警 ID xdr-alert-001/002、事件 ID evt-97bccf8a… 全是样例虚构/本链生成的 ID，真实 dbproxy 库无这些实体 → 合法空集。
3. **MCP 服务连接失败被跳过（深度调查环节 → MCP 工具注册/初始化）**：每个地址先 `initialize()` 再 `list_tools()`，任一失败打印 `[warn]` 并跳过该服务全部工具。真实 MCP 地址属内网敏感信息不入库，需本地 `MCP_URLS`/`mcp_servers.local.json`；未配置/不可达/证书校验（默认已关）都会导致跳过。
4. **审批接口 body 解析失败（人工审批环节 → 前端 REST 接口）**：Windows curl 命令行直接写 UTF-8 中文 JSON 传送到服务器损坏，FastAPI 解析失败；非后端逻辑问题（换 ASCII 字段或 Swagger UI 输中文即通过）。
5. **主链启动报 `ZoneInfoNotFoundError: Asia/Shanghai`（服务启动环节）**：Windows Python 缺 `tzdata` 包，`pip install tzdata` 解决。

**一句话根因**：真实 LLM 轮的 8 次「失败/空」全发生在深度调查环节的工具采集侧——Mock 侧是「演示数据只认识 192.168.1.100，样例 IP 查不到」，MCP 侧是「查的实体是样例虚构的，真实库没有」，本质同源：**LLM 拿样例虚构实体去查真实/有限的数据源**。而 `tool_mock` 内部子链（`evidence_lookup`/`xdr_log_query`）走 fixed_sample 自带种子数据，无任何工具失败，所以能顺利走到审批→执行→COMPLETED。

### 10.2 上游问题分析（2026-08-26）

结论：5 个问题里 ① 和 ② 是链路上游问题，根因同源——出在**样例数据装配（平台接入 RECEIVED 阶段）**；③ 是「深度调查环节内部更早一步」；④⑤ 不是数据链路问题。

| # | 问题 | 表现环节 | 根因环节 | 是链路上游？ |
|---|------|---------|---------|------------|
| ① | Mock 数据不可得 | INVESTIGATING | **RECEIVED（样例数据装配）** | ✅ 上游（同源） |
| ② | dbproxy 空数据 | INVESTIGATING | **RECEIVED（样例数据装配）** | ✅ 上游（同源） |
| ③ | MCP 连接失败跳过 | INVESTIGATING（工具注册） | 本环节工具装配 / 环境配置 | ⚠️ 环节内部，非链路上游 |
| ④ | 审批 body 解析失败 | APPROVAL（链路下游） | 客户端（Windows curl 编码） | ❌ |
| ⑤ | tzdata 缺失 | 启动（链路之前） | 环境依赖 | ❌ |

核心含义：① ② 的「证据不足 → 人工接管」本质是**上游喂了虚构样例实体**，不是调查链路或工具的问题。真实接入时事件来自真实库，这两个问题会同时消失。这也解释了为什么 `tool_mock` 内部子链那轮没失败——它走的是 fixed_sample **自带种子数据**（上游数据源一致），所以一路走通到 COMPLETED。

## 11. 28 日真实平台联调步骤（调查阶段）

面向 8 月 28 日真实平台工具接入，与杨嘉琪对齐 dbproxy 等真实工具契约后，按以下清单执行联调。目标：证明真实平台工具按约定返回后，调查 Agent 能正常消费；真实调用失败时能按预期 fallback。

### 11.1 所需配置

| 配置项 | 来源 | 说明 |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 环境变量或 `llm_config.local.json`（gitignore） | 深度调查推理；未配置则 agent 报错 |
| `MCP_URLS`（或 `mcp_servers.local.json`） | 环境变量 / gitignore 本地文件 | 5 个深信服 MCP 服务地址，真实地址不入库 |
| `MCP_API_KEY`（可选） | 同上 | MCP 鉴权；多数 dbproxy 服务带 `apikey` 头 |
| `MCP_VERIFY_SSL`（可选） | 同上 | 默认关闭证书校验（内网自签） |
| `INVESTIGATION_BACKEND=auto` | 环境变量 | 主链调查后端：bridge 优先，失败回退内部子链 |
| `PYTHONPATH=src` | 环境变量 | 保证 `sec_agent` 可导入 |
| `tzdata` | `pip install tzdata` | Windows 必需，否则主链 import 报 `ZoneInfoNotFoundError` |

### 11.2 调用入口

```text
# ① CLI 独立调查（最快验证工具消费，无需起服务）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

# ② 主链 HTTP 联调（真实事件经 RECEIVED→…→INVESTIGATING 触发调查）
$env:INVESTIGATION_BACKEND="auto"; $env:PYTHONPATH="src"; python -m uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
#   POST /runs  body {"source":"<真实平台接入源>","sample_id":"<真实事件ID>"}
#   观察 GET /events/{id}/timeline 中 INVESTIGATING 阶段
```

### 11.3 预期工具调用（真实平台）

WebShell 类事件典型调用序列，按证据缺口推进：

| 步骤 | 工具（真实名） | 输入 | 成功返回 | 空结果（本模块识别为） |
|---|---|---|---|---|
| 1 查资产 | `dbproxy_资产数据查询工具` | `{"param":{"query_type":"detail","request_body":{"filter":{...ip...},"limit":10}}}` | `{"code":0,"data":[{资产字段...}]}` → `success` | `{"code":0,"data":[]}` → `partial` |
| 2 查告警 | `dbproxy_告警数据查询工具` | 同上（告警 filter/sort/size） | `data` 非空 → `success` | `data:[]` → `partial` |
| 3 查漏洞 | `dbproxy_脆弱性数据查询工具` | `{"filter":{"asset":ip,"data_type":"loophole"},"limit":20}` | `data` 非空 → `success` | `data:[]` → `partial` |
| 4 查威胁实体 | `dbproxy_威胁实体数据查询工具` | `{"filter":{"operationTarget.nodeInfo.ip":src}}` | `data` 非空 → `success` | `data:[]` → `partial` |
| 5 研判 | `secgpt_告警事件解读研判` / `secgpt_威胁实体的调查分析` | `{"content":事件描述}` | 研判文本 → `success`（无 code/data 结构） | 文本为空 → 视文本内容 |
| 6 知识包 | `knowledge_query` | `{"keyword":"WebShell处置建议"}` | 命中条目 + `evidence_refs` → `success` | 无关词 → `failed` |

> dbproxy 契约要点：`code==0` 且 `data` 为空 → `partial`（查询成功但无数据）；`code!=0` → `failed`（业务错误，`msg` 为错误信息）；`code==0` 且 `data` 非空 → `success`。三种状态经 `ToolResult.to_str()` 分别以「[部分成功] / [失败] / 原文」回填给 LLM，使其按「数据为空」触发停止条件而非静默成功。

### 11.4 工具记录检查（`tool_call_records`）

报告 JSON 的 `tool_call_records` 由代码侧真实采集，逐条核对：

| 检查项 | 通过标准 |
|---|---|
| 工具名 | 为真实名（如 `dbproxy_告警数据查询工具`），非 ASCII 内部别名 |
| `status` | 只出现 `success` / `partial` / `failed` 三态；空数据必须是 `partial` 而非 `success` |
| `output` | 与真实平台返回一致；空数据 output 为 `[部分成功] 查询成功但无数据` |
| `knowledge_query` 记录 | 命中时含 `evidence_refs` 结构化字段 |
| 调用次数 | 不超过 `AGENT_MAX_TOOL_CALLS`（默认 12） |

### 11.5 调查报告检查

| 检查项 | 通过标准 |
|---|---|
| `evidence_source` | 含知识包引用（如 `CISA Eliminate Web Shells (CM0106)`）与真实工具来源 |
| `key_evidence` | 有具体数据支撑，无「数据不可得」当作真实证据编造 |
| `confidence` | 随证据合理调整（0~1），空结果不抬高置信度 |
| `need_manual_takeover` | 关键工具 `partial`/`failed` 且证据不足时置 `true` |
| `disposal_suggestions` | 由知识包处置模板驱动（CISA CM0106 流程），不自动执行 |

### 11.6 真实平台失败时的 fallback

| 失败情形 | 表现 | fallback 行为 |
|---|---|---|
| MCP 服务连接失败 | 注册阶段 `[warn] MCP 服务「xxx」连接失败，跳过` | 该服务全部工具跳过，仅剩 Mock + 知识包 + 其它可达服务 |
| dbproxy 返回空数据 | `partial`（查询成功但无数据） | 回填 LLM → 触发「数据为空」停止条件 → 人工接管 |
| dbproxy 业务错误 `code!=0` | `failed`（`msg` 为错误信息） | 回填 LLM → 记录「数据不可得」→ 不编造证据 |
| 全部真实工具不可达 | `--list-tools` 仅剩 Mock + 知识包 | 调查仍可产出报告，但证据来自 Mock/知识包，`need_manual_takeover` 置 `true` |
| LLM 未配置 | agent 抛「LLM 未配置」 | 主链 `auto` 后端回退内部子链（`evidence_lookup`+`xdr_log_query`） |

> 联调核心判据：真实平台按契约返回（`code==0`+数据 / `code==0`+空 / `code!=0`）后，`tool_call_records` 的 `status` 分别正确落为 `success` / `partial` / `failed`，且报告结论、置信度、人工接管标记随之变化——即证明「真实工具返回真正影响证据与结论」，而非仅证明函数可导入。

## 12. 变更记录

| 日期 | PR/Commit | 变更内容 |
|---|---|---|
| 2026-08-24 | PR #13 | 子智能体落地，建立首版测试 |
| 2026-08-25 | `383fec7` | bridge 双包名修复 + 回归用例 |
| 2026-08-25 | `3c49db2` | `-o` 报告时间戳 |
| 2026-08-26 | 本次 T0826-03 提交 | 新增 `test_knowledge_tool.py`（19 用例）；本文件按模板重写并补本轮复验（真实加载 / 工具调用 / 结构化报告 / fallback 实际结果） |
| 2026-08-26 | 本次（方案 C 提交） | 新增降级报告提炼与 AgentConfig 步数上限用例；执行命令预期更新为 47 passed / 1 skipped |
| 2026-08-27 | 本次 T0827-03 提交 | 知识源统一到沈洪旭权威版；新增 `test_mcp_client.py`（11 用例）验证 dbproxy 空结果 `partial` / 结构化错误 `failed` / 有数据 `success` 契约 |
| 2026-09-04 | PR #31收口 | `test_mcp_client.py`扩至18例：补非dbproxy空文本、MCP `isError`、error JSON、已知错误文本及正常分析含错误词不误判 |
