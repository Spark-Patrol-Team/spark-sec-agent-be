# 深度调查 Agent 模块开发说明

## 代码位置

- 子智能体完整实现：`deep_agent/`（独立可运行包）
- 主链占位接入：`src/sec_agent/services/investigation.py`

## 模块组成

`deep_agent/` 是 LLM 驱动的深度调查子智能体，落地设计文档中的「调查闭环」：

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

## 配置（环境变量）

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BASE_URL` | LLM 接口地址（OpenAI 兼容） | `https://api.deepseek.com` |
| `LLM_API_KEY` | LLM 密钥 | `sk-xxx` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `TOOL_MODE` | `mock` / `mcp` / `auto`（默认） | `auto` |
| `MCP_API_KEY` | 深信服 MCP apikey（漏洞查询等需要） | — |

> 凭据只从环境变量读取，不写进代码，符合「凭据不进入源码」的工程约束。

## 启动 / 运行

```bash
# 1. 查看可用工具（无需 LLM key）
python -m deep_agent.main --event test/sample_event.json --list-tools

# 2. 完整调查（需 LLM key，结果写到 report.json）
python -m deep_agent.main --event test/sample_event.json -o report.json
```

## 与主链集成状态

- 主链 `Orchestrator` 在 `INVESTIGATING` 阶段调用 `src/sec_agent/services/investigation.py` 的占位 `DeepInvestigationAgent`。
- 本 `deep_agent/` 是完整的 LLM 深度调查子智能体，尚未桥接到主链（`services/investigation.py` 仍为占位单步查询）。
- 桥接待办：将 `deep_agent` 的调查循环 / 工具调用适配到仓库 `domain.models` 的 `SecurityEvent` / `TriageResult` / `InvestigationReport` 与 `PlatformAdapter.run_tool` 契约。

## 已知问题

1. 4 个内网 MCP 地址在代码中以 `<internal-mcp-host>` 占位，仅深信服平台内网可解析，本地会自动跳过。
2. 公网「漏洞信息查询」可连接并列出工具，真实调用需 `MCP_API_KEY`。
3. Mock 数据仅覆盖 WebShell 主场景，其他场景需补充。
