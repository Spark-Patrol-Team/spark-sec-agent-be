# 深度调查 Agent 模块开发说明

## 代码位置

- 子智能体完整实现：`src/sec_agent/deep_agent/`（`sec_agent.deep_agent` 子包，独立可运行）
- 主链占位接入：`src/sec_agent/services/investigation.py`
- 测试：`tests/test_investigation_agent.py` + 样例 `tests/fixtures/investigation/sample_event.json`

## 模块组成

`sec_agent.deep_agent` 是 LLM 驱动的深度调查子智能体，落地设计文档中的「调查闭环」：

| 文件 | 职责 |
|------|------|
| `agent.py` | 调查循环（ReAct 风格）：接收事件 → 分析证据 → 识别缺口 → 调工具 → 更新结论 → 停止判断 → 输出报告 |
| `models.py` | 输入 `SecurityEventInput` / 输出 `InvestigationReport` 数据模型 |
| `config.py` | LLM / 工具 / Agent 参数配置（环境变量驱动，凭据不入源码） |
| `llm.py` | LLM 客户端（OpenAI 兼容接口） |
| `main.py` | 命令行入口 |
| `tools/base.py` | 工具抽象基类 + 注册表 + 统一结果 |
| `tools/mock.py` | Mock 工具（6 个，无真实平台时兜底） |
| `tools/mcp_client.py` | 最小 MCP 客户端（连深信服 MCP，兼容 JSON 与 SSE） |

## 依赖

- Python 3.11+（与仓库一致）
- `openai`（LLM 调用）、`requests`（MCP 调用）

```bash
pip install openai requests
```

## 配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BASE_URL` | LLM 接口地址（OpenAI 兼容） | `https://api.deepseek.com` |
| `LLM_API_KEY` | LLM 密钥 | `sk-xxx` |
| `LLM_MODEL` | 模型名（默认 `deepseek-chat`） | `deepseek-chat` |
| `LLM_TEMPERATURE` | LLM 采样温度（默认 `0.0`） | `0` |
| `LLM_TIMEOUT` | LLM 请求超时秒数（默认 `90`） | `90` |
| `TOOL_MODE` | `mock` / `mcp` / `auto`（默认） | `auto` |
| `MCP_URLS` | 深信服 MCP 地址（JSON），未设时读本地文件 | 见下 |
| `MCP_API_KEY` | 深信服 MCP apikey（漏洞信息查询等需要，可选） | — |
| `MCP_VERIFY_SSL` | 是否校验 MCP HTTPS 证书（自签证书默认 `0` 关闭） | `0` |

> LLM API 配置支持三种来源（优先级从高到低）：
> 1. 环境变量：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（另支持 `LLM_TEMPERATURE` / `LLM_TIMEOUT`）
> 2. 本地文件：`src/sec_agent/deep_agent/llm_config.local.json`（已 gitignore，含 apikey，不入库）
> 3. 默认值（模型默认 `deepseek-chat`）
>
> 可用可视化界面配置本地文件（见下文「API 可视化配置界面」），或手动编辑 JSON。

> 真实 MCP 地址属内网敏感信息，不入库。两种本地配置方式（二选一）：
> 1. 环境变量：`MCP_URLS='{"漏洞信息查询":"https://..."}'`
> 2. 本地文件：`src/sec_agent/deep_agent/mcp_servers.local.json`（已 gitignore，格式 `{"服务名":"地址"}`）
>
> 未配置时只跑 Mock 工具，真实 MCP 工具跳过。

## 工具说明

Mock 工具（`TOOL_MODE=mock`）内置 WebShell 主场景模拟数据，用于演示「工具无数据 → 人工接管」边界：`query_asset` / `query_alerts` / `query_vulnerabilities` / `secgpt_analyze` / `attack_detect` / `vuln_intelligence`。

真实 MCP 工具（`TOOL_MODE=mcp` / `auto`）连接深信服 5 个 FastGPT 托管的 MCP 服务，实测工具如下：

| MCP 服务 | 工具 |
|----------|------|
| 漏洞信息查询 | `vuln_search_intelligence_tool` / `vuln_highlevel_intelligence_tool` / `vuln_hot_intelligence_tool` / `vuln_vpt_tool` |
| 检测大模型 | `cybersec_攻击状态检测` / `cybersec_攻击类型检测` |
| 网络安全数据查询 | 事件 / 告警 / 漏洞 / 弱密码 / 资产关联漏洞 / 资产 查询统计 |
| 运营大模型 | `secgpt_告警事件解读研判` / `secgpt_威胁实体的调查分析` |
| 自由数据查询 | `dbproxy_事件/告警/脆弱性/资产/威胁实体 数据查询` |

服务走 HTTPS + 自签证书，客户端默认关闭证书校验；地址连不上时自动跳过（打印 `[warn]`），不影响 Mock 兜底。

## 启动 / 运行

```bash
# 1. 查看可用工具（无需 LLM key）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json --list-tools

# 2. 完整调查（需 LLM key；-o 报告名自动加时间戳，如 report.json → report_20260825_160543.json，不覆盖旧报告）
PYTHONPATH=src python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json
```

## API 可视化配置界面

提供 tkinter 图形界面，用于配置 LLM API（地址 / 密钥 / 模型名 / 温度 / 超时），并支持一键保存与清除：

```bash
PYTHONPATH=src python -m sec_agent.deep_agent.config_gui
```

- **保存**：写入 `src/sec_agent/deep_agent/llm_config.local.json`（含 apikey，已 gitignore，不入库）。
- **清除**：删除该本地配置文件并清空输入框。
- 界面管理的仅是本地文件；若同时设置了 `LLM_*` 环境变量，环境变量优先级更高。
- 相关函数：`config.save_api_config()` / `config.clear_api_config()` / `config.load_api_config_file()`。

## 与主链集成状态

- 主链 `Orchestrator` 在 `INVESTIGATING` 阶段调用 `src/sec_agent/services/investigation.py` 的 `DeepInvestigationAgent`，支持 3 个后端（`INVESTIGATION_BACKEND`：`auto` 默认 / `deep_agent` / `tool_mock`）。
- `auto` / `deep_agent` 后端经 `services/deep_agent_bridge.py` 的 `DeepAgentBridge` 桥接 `sec_agent.deep_agent`（构造工具、要求 LLM 可用、领域模型互转）；`auto` 在 bridge 不可用 / 异常时回退**内部工具调查子链**（`evidence_lookup` + `xdr_log_query`，经 `PlatformAdapter`，无 LLM）；`tool_mock` 仅内部子链。
- **已修复（2026-08-25）**：bridge 原以 `importlib.import_module("deep_agent.*")` 导入不存在的顶层包，已改为 `sec_agent.deep_agent.*`（方案 A），并补回归测试 `test_bridge_loads_real_deep_agent_modules`。
- **修复后实测（`auto` 后端，`TOOL_MODE=mock`，配置 LLM）**：bridge 真实加载 PR #13 Agent、实际调用 LLM，7 次 Mock 工具调用，输出完整结构化报告，未发生内部 fallback；WebShell 样例下报告标记人工接管 → 主链停在 HUMAN_REQUIRED（此前回退子链会直接自动处置至 COMPLETED）。

### 复验结果（2026-08-25）

- **独立运行 `sec_agent.deep_agent`（复验通过）**：main 可真实加载 PR #13 Agent；`TOOL_MODE=mock` 完整调查一轮，6 个 Mock 工具实际调用 7 次，生成完整结构化报告（结论 / 证据 / 攻击链 / 处置建议 / 置信度 0.86），退出码 0；**实际调用 LLM**；**未发生内部 fallback**（`need_manual_takeover=true` 为正常业务标记）。`tests/test_investigation_agent.py` 16 passed / 1 skipped。
- **主链 `run_flow.py`（实测）**：补装 `tzdata` 后可全流程跑通；bridge 导入路径修复后，`auto` 后端**真实加载 PR #13 Agent + 实际调用 LLM + 7 次 Mock 工具调用**，生成完整结构化报告、未发生内部 fallback；WebShell 样例下报告标记人工接管 → 主链停在 HUMAN_REQUIRED。
- **环境**：Windows Python 需补装 `tzdata`（否则主链 import 即报 `ZoneInfoNotFoundError: Asia/Shanghai`）；`fastapi` / `sqlalchemy` / `pymysql` 为主链全链依赖，deep_agent 独立运行只需 `openai` / `requests`。

## 已知问题

1. 深信服 MCP 真实地址不入库，需本地配置 `MCP_URLS` 或 `mcp_servers.local.json`，否则真实 MCP 工具跳过、仅 Mock 可用。
2. MCP 走 HTTPS 自签证书，客户端默认关闭证书校验（`MCP_VERIFY_SSL=0`）。
3. Mock 数据仅覆盖 WebShell 主场景，其他场景需补充。
4. Windows Python 缺 `tzdata` 时主链 import 即失败（`ZoneInfoNotFoundError: Asia/Shanghai`），需 `pip install tzdata`。
