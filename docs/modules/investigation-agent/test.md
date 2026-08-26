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
| `src/sec_agent/deep_agent/knowledge/webshell_min.md` | 人工构造（知识包最小集） | 攻击原理 / 特征速查 / 工具流量 / 检查清单 / 处置建议 / 人工接管 |
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

### 5.3 bridge 集成（`tests/test_investigation_and_dispatcher_integration.py`）

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

## 7. 执行方式（真实执行命令）

```bash
# 单元 + 集成测试（不依赖 LLM key 的部分稳定通过）
PYTHONPATH=src python -m pytest tests/test_knowledge_tool.py tests/test_investigation_agent.py tests/test_investigation_and_dispatcher_integration.py -q
#   预期：42 passed / 1 skipped（1 项为需 LLM key 的集成用例）

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
| 知识包纳入 git 提交 | ✅ `webshell_min.md` 入库，`knowledge_query` 随本次提交 |

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

## 11. 变更记录

| 日期 | PR/Commit | 变更内容 |
|---|---|---|
| 2026-08-24 | PR #13 | 子智能体落地，建立首版测试 |
| 2026-08-25 | `383fec7` | bridge 双包名修复 + 回归用例 |
| 2026-08-25 | `3c49db2` | `-o` 报告时间戳 |
| 2026-08-26 | 本次 T0826-03 提交 | 新增 `test_knowledge_tool.py`（19 用例）；本文件按模板重写并补本轮复验（真实加载 / 工具调用 / 结构化报告 / fallback 实际结果） |
