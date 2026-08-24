# 深度调查 Agent 使用教程

面向：Windows 11 + PowerShell 环境。全程用本教程即可跑通「配置 API → 运行调查 → 看报告」完整链路。

---

## 1. 这是什么

一个 **LLM 驱动的深度调查子智能体**（`sec_agent.deep_agent`）：接收一个安全事件 → 自主分析证据缺口 → 调用安全工具补证 → 更新结论 → 输出结构化调查报告。

工具来源：**6 个 Mock 兜底工具 + 19 个深信服真实 MCP 工具**（配置齐全时共 25 个可用）。

代码位置：`src/sec_agent/deep_agent/`

---

## 2. 环境准备

```powershell
# ① Python 版本（仓库要求 >=3.11）
python --version

# ② 安装依赖（只需两个）
pip install openai requests
```

> 需要 GUI 配置界面的话无需额外安装：tkinter 是 Python 自带的。

---

## 3. 快速上手（3 步跑通）

```powershell
cd C:\Users\dell\Desktop\spark-sec-agent-be

# ① 打开 API 配置界面，填入模型地址/密钥/模型名 → 点「保存配置」
$env:PYTHONPATH = "src"; python -m sec_agent.deep_agent.config_gui

# ② 跑一次完整调查（用自带样例）
$env:PYTHONPATH = "src"; python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

# ③ 打开 report.json 看调查报告
```

---

## 4. API 配置（LLM 地址/密钥/模型名）

有三种方式，**优先级：环境变量 > 本地配置文件 > 默认值**。

### 4.1 可视化界面（推荐）

```powershell
$env:PYTHONPATH = "src"; python -m sec_agent.deep_agent.config_gui
```

弹出窗口，填 5 个字段：

| 字段 | 填什么 | 示例（DeepSeek） |
|------|--------|------------------|
| 模型地址 Base URL | LLM 接口地址 | `https://api.deepseek.com` |
| API 密钥 | 你的密钥（输入时显示 `*`） | `sk-xxxxxxxx` |
| 模型名称 | 模型名 | `deepseek-chat` |
| 温度 Temperature | 一般 `0` | `0` |
| 超时秒数 | 一般 `90` | `90` |

- **保存**：写入 `src/sec_agent/deep_agent/llm_config.local.json`（含密钥，已 gitignore，不入库）
- **清除**：删除该文件并清空输入框

### 4.2 手动编辑配置文件

文件：`src/sec_agent/deep_agent/llm_config.local.json`

```json
{
  "base_url": "https://api.deepseek.com",
  "api_key": "sk-xxxxxxxx",
  "model": "deepseek-chat",
  "temperature": 0.0,
  "timeout": 90
}
```

### 4.3 环境变量（PowerShell 临时设置）

```powershell
$env:LLM_BASE_URL = "https://api.deepseek.com"
$env:LLM_API_KEY = "sk-xxxxxxxx"
$env:LLM_MODEL = "deepseek-chat"
# 可选：$env:LLM_TEMPERATURE = "0"; $env:LLM_TIMEOUT = "90"
```

### 4.4 常见模型地址（OpenAI 兼容，任选一家）

| 厂商 | Base URL | 模型名示例 |
|------|----------|-----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` / `deepseek-reasoner` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` / `qwen-max` |
| 月之暗面 | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |

> 只要是 OpenAI 兼容接口都能用。未配置时运行会提示 `LLM 未配置`。

---

## 5. 深信服 MCP 配置（真实安全工具）

真实内网地址**不入库**，两种方式二选一：

**方式一：环境变量**
```powershell
$env:MCP_URLS = '{"漏洞信息查询":"https://<内网地址>","检测大模型":"https://<内网地址>"}'
```

**方式二：本地文件**
`src/sec_agent/deep_agent/mcp_servers.local.json`（已 gitignore）：
```json
{
  "漏洞信息查询": "https://<内网地址>",
  "检测大模型": "https://<内网地址>"
}
```

相关环境变量：

| 变量 | 作用 | 默认 |
|------|------|------|
| `TOOL_MODE` | `mock` / `mcp` / `auto` | `auto` |
| `MCP_API_KEY` | 漏洞信息查询等服务需要的 apikey（可选） | 空 |
| `MCP_VERIFY_SSL` | 是否校验证书（自签证书环境设 `0`） | `0` |

> 地址没配或连不上时，自动只跑 Mock 工具（6 个），真实 MCP 工具跳过并打印 `[warn]`。

---

## 6. 运行调查

```powershell
# 查看当前可用工具（无需 LLM key）
$env:PYTHONPATH = "src"; python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json --list-tools

# 跑完整调查（需已配置 API），结果写 report.json
$env:PYTHONPATH = "src"; python -m sec_agent.deep_agent.main --event tests/fixtures/investigation/sample_event.json -o report.json

# 不指定 -o 则结果直接打印到屏幕
```

| 参数 | 作用 | 必填 |
|------|------|------|
| `--event <文件>` | 待调查的安全事件 JSON 路径 | ✅ |
| `-o / --output <文件>` | 报告输出文件 | 否 |
| `--list-tools` | 只列工具清单 | 否 |

> Git Bash 用户把 `$env:PYTHONPATH = "src";` 换成 `PYTHONPATH=src ` 前缀即可。

---

## 7. 输入事件格式（`--event` 指向的 JSON）

样例：`tests/fixtures/investigation/sample_event.json`

```json
{
  "event_id": "EVENT-001",
  "event_type": "WebShell",
  "severity": "HIGH",
  "timestamp": "2026-08-22 10:23:15",
  "source_ip": "10.10.10.25",
  "target_ip": "192.168.1.100",
  "alerts": ["WebShell通信行为告警"],
  "evidence": ["检测到疑似WebShell通信"],
  "initial_verdict": "疑似真实攻击",
  "confidence": 0.72,
  "triage": {"verdict": "malicious", "confidence": 0.72},
  "trace_id": "trace-001",
  "run_id": "run-001"
}
```

核心字段：`event_id` / `event_type` / `severity` / `timestamp` / `source_ip` / `target_ip` / `alerts` / `evidence` / `initial_verdict` / `confidence`；`triage`、`trace_id`、`run_id` 可选。未知字段自动忽略。

> 换调查对象：改这个 JSON 里的攻击源、目标、告警、证据即可，其余不用动。

---

## 8. 输出报告说明（report.json）

关键字段：

| 字段 | 含义 |
|------|------|
| `conclusion` | 调查结论 |
| `risk_level` / `attack_type` | 风险等级 / 攻击类型 |
| `key_evidence` / `evidence_source` | 关键证据 / 证据来源 |
| `investigation_steps` | 调查步骤（含每步目标、证据缺口、调用的工具与输入输出） |
| `tool_call_records` | 工具调用记录（真实采集，可审计） |
| `attack_chain` | 攻击链描述 |
| `confidence` | 调查置信度 0~1 |
| `disposal_suggestions` | 处置建议 |
| `need_manual_takeover` | 是否需人工接管（true 时看 `manual_takeover_reason`） |

> 若结果为「证据不足，人工接管」，说明工具返回的数据不够支撑结论（或调查到上限仍无充分证据），属正常兜底行为。

---

## 9. 工具清单（共 25 个）

**6 个 Mock**：`query_asset` / `query_alerts` / `query_vulnerabilities` / `secgpt_analyze` / `attack_detect` / `vuln_intelligence`

**19 个深信服 MCP**：

| MCP 服务 | 工具 |
|----------|------|
| 漏洞信息查询 | `vuln_search_intelligence_tool` 等 4 个 |
| 检测大模型 | `cybersec_攻击状态检测`、`cybersec_攻击类型检测` |
| 网络安全数据查询 | 事件/告警/漏洞/弱密码/资产关联/资产 查询统计 6 个 |
| 运营大模型 | `secgpt_告警事件解读研判`、`secgpt_威胁实体的调查分析` |
| 自由数据查询 | `dbproxy_*` 数据查询 5 个 |

> 中文名的 MCP 工具发给 LLM 时使用 ASCII 内部别名（如 `cybersec_attack_status_detect`），调用后自动还原，无需你关心。映射表见 `design.md`。

---

## 10. 常见问题排查

| 现象 | 原因与处理 |
|------|-----------|
| 报 `LLM 未配置` | 没配 API。用 GUI 保存或设 `LLM_*` 环境变量 |
| 报 `Invalid function.name` 400 | 老版本中文工具名问题，已修复；确认在最新分支 |
| 报 `ModuleNotFoundError: sec_agent` | 忘了 `$env:PYTHONPATH = "src"` |
| 提示 `MCP 服务连接失败，跳过` | 地址/网络问题，检查 `mcp_servers.local.json`；只影响真实工具，Mock 仍可用 |
| 控制台中文乱码 | Windows 控制台编码显示问题，不影响运行与报告内容 |
| 报告写不进去 / 目录不存在 | 确认 `-o` 指向的目录已存在 |
| 推送 GitHub 超时 | 网络问题（GitHub 直连不稳），重试即可，与代码无关 |
| 跑 `tests/test_state_flow` 报 `ZoneInfoNotFoundError: Asia/Shanghai` | Windows Python 缺 tzdata 的已知环境问题，与本模块无关 |

---

## 11. 目录速查

```
src/sec_agent/deep_agent/
├── main.py           命令行入口
├── config.py         配置加载（LLM/MCP/Tool）
├── config_gui.py     API 可视化配置界面
├── agent.py          调查闭环（LLM 驱动）
├── llm.py            LLM 客户端（OpenAI 兼容）
├── models.py         输入事件 / 输出报告模型
├── tools/
│   ├── base.py       工具基类 + 注册表 + 内部别名层
│   ├── mock.py       6 个 Mock 工具
│   └── mcp_client.py 深信服 MCP 客户端（19 个真实工具）
├── mcp_servers.local.json  深信服 MCP 地址（gitignore）
└── llm_config.local.json   LLM API 配置（gitignore）
```
