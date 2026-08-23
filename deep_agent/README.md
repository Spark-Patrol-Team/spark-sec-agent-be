# 深度调查 Agent

面向高风险、疑似真实攻击或证据不足的安全事件，在已有风险研判基础上主动补充证据、验证攻击判断，输出结构化调查报告。

## 一、目录结构

```
deep_agent/
├── agent.py          # Agent 核心：调查循环 / 停止条件 / 报告生成
├── models.py         # 数据模型：SecurityEventInput / InvestigationReport
├── config.py         # 配置：LLM / MCP 地址 / Agent 参数
├── llm.py            # LLM 客户端（OpenAI 兼容接口）
├── main.py           # 命令行入口
├── tools/
│   ├── base.py       # 工具抽象基类 + 注册表 + 统一结果
│   ├── mock.py       # Mock 工具（无真实平台时兜底）
│   └── mcp_client.py # 最小 MCP 客户端（连深信服 MCP 服务）
└── README.md
test/
├── sample_event.json # WebShell 固定样例
└── test_agent.py     # 单元测试 + 集成测试
```

## 二、依赖

- Python 3.9+
- `openai`（LLM 调用）、`requests`（MCP 调用）

```bash
pip install openai requests
```

## 三、配置（环境变量）

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BASE_URL` | LLM 接口地址（OpenAI 兼容） | `https://api.deepseek.com` |
| `LLM_API_KEY` | LLM 密钥 | `sk-xxx` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `TOOL_MODE` | 工具模式：`mock` / `mcp` / `auto` | `auto`（默认） |
| `MCP_API_KEY` | 深信服 MCP 服务 apikey（漏洞查询等需要） | — |

> 凭据只从环境变量读取，不写进代码/文档，符合「凭据不进入源码」的工程约束。

## 四、运行

```bash
# 1. 查看当前可用工具
python -m deep_agent.main --event test/sample_event.json --list-tools

# 2. 跑一次完整调查（结果打印到控制台）
python -m deep_agent.main --event test/sample_event.json

# 3. 结果写到文件
python -m deep_agent.main --event test/sample_event.json -o report.json
```

Windows 下设置环境变量（PowerShell）示例：

```powershell
$env:LLM_BASE_URL = "https://api.deepseek.com"
$env:LLM_API_KEY  = "sk-xxx"
$env:LLM_MODEL    = "deepseek-chat"
```

## 五、工具说明

### Mock 工具（`TOOL_MODE=mock`）
内置 WebShell 主场景模拟数据，目标 IP `192.168.1.100` 有数据，其余 IP 返回「数据不可得」，用于演示「工具无数据 → 人工接管」边界：

| 工具 | 能力 |
|------|------|
| `query_asset` | 查目标资产信息 |
| `query_alerts` | 查相关告警 |
| `query_vulnerabilities` | 查资产漏洞 |
| `secgpt_analyze` | 安全GPT研判（模拟） |
| `attack_detect` | 攻击类型/结果检测 |
| `vuln_intelligence` | 漏洞情报查询 |

### 真实 MCP 工具（`TOOL_MODE=mcp` / `auto`）
连接深信服 5 个 MCP 服务（地址见 `config.py`）。注意：

- 仅「漏洞信息查询」是公网地址，配 `MCP_API_KEY` 后可真实调用；
- 其余 4 个是深信服平台内网地址（代码中以 `<internal-mcp-host>` 占位，需在平台内网部署时替换），本地连不上，会自动跳过；
- `auto` 模式 = Mock 兜底 + 连上的真实 MCP 并存，符合设计文档「真实能力 + Mock，逐步替换」策略。

## 六、测试

```bash
python -m unittest test.test_agent -v
```

- 单元测试（模型 / Mock 工具 / JSON 提取 / 降级报告）不依赖 LLM，可直接跑。
- 集成测试 `TestFullInvestigation` 需配置 `LLM_API_KEY` 后才会执行，验证完整调查闭环。

## 七、模块契约（对齐《统一接口与数据流》）

| 项 | 内容 |
|----|------|
| 输入 | `SecurityEventInput`（设计文档 10 字段 + `triage` 风险研判结果） |
| 输出 | `InvestigationReport`（调查结论、置信度、证据、调查步骤、工具调用、处置建议、是否人工接管等） |
| 安全边界 | 不推进业务状态；不绕过工具适配层直连平台；不执行高风险处置动作 |

## 八、调查闭环与停止条件

```
接收事件 → 分析证据 → 识别缺口 → 规划 → 调工具 → 补证据 → 更新结论 → 停止判断 → 输出报告
```

停止条件（满足任一即结束）：证据充分 / 步数 ≥ 5 / 工具无法获得数据。
人工接管条件：高风险+证据不足+关键工具失败 / 结果明显冲突 / 高风险处置动作。

## 九、已知限制（后续迭代）

1. MCP 客户端为最小实现，仅覆盖 `initialize` / `tools/list` / `tools/call`，未做完整的协议版本协商与重试。
2. Mock 数据仅覆盖 WebShell 主场景，其他场景需补充模拟数据。
3. 调查步骤 `investigation_steps` 由 LLM 复盘生成，工具调用 `tool_call_records` 由代码真实采集。
