
# 深度调查 Agent 模块设计

## 模块职责

根据安全事件和风险研判结果规划调查步骤、调用工具补充证据，并输出结构化调查报告。


## 安全边界

- 不直接推进业务状态。
- 不直接绕过工具适配层调用真实平台。
- 不执行高风险处置动作。


# 深度调查agent设计

# 总览

目标链路：

**真实安全事件 → Agent识别缺口 → 真实深信服工具调用 → 获得真实证据 → Agent更新结论 → 输出结构化报告。**

## 输入（依赖 XDR事件数据、格式以及深度调查前的其他产生数据）



```Plain Text
事件ID
事件类型
风险等级
事件时间
攻击源
目标资产
已有告警
已有证据
初步风险研判
研判置信度
```



### 输出（即生成的报告）

Agent 输出结构化调查结果，包括内容：

```Plain Text
事件基本信息
调查结论
风险等级
攻击类型
关键证据
证据来源
调查步骤
工具调用记录
攻击链/攻击过程
调查置信度
处置建议
是否需要人工接管
```



### 依赖（目前能想到的）

1. XDR OpenAPI具体接口

2. API认证方式

3. MCP工具清单及参数。或者是其他低代码工具、相关安全工具

4. XDR事件数据、格式

5. 安全GPT调用方式/权限

6\.知识库补充（mvp是否考虑待定）



### 第一版最小调查流程：

安全事件
   ↓
Agent接收事件
   ↓
分析已有证据
   ↓
识别证据缺口
   ↓
规划下一步调查
   ↓
调用安全工具，待探索
   ↓
获取补充证据
   ↓
更新调查结论
   ↓
判断是否满足停止条件
   ↓
输出结构化调查报告



### 实际链路

等客服回复后研究

# 深度调查 Agent 第一版设计文档

## 功能定位

### 1\.1 目标

深度调查 Agent 面向**高风险、疑似真实攻击或现有证据不足的安全事件**，负责在已有风险研判结果基础上进一步补充证据、验证攻击判断，并形成结构化调查结论。

# Agent 输入与输出

## 2\.1 输入

Agent 接收上游风险研判后的**标准化安全事件**。

建议第一版统一为：

```Plain Text
事件ID
事件类型
风险等级
事件时间
攻击源
目标资产
已有告警
已有证据
初步风险研判
研判置信度
```

例如：

```JSON
{
  "event_id": "EVENT-001",
  "event_type": "WebShell",
  "severity": "HIGH",
  "timestamp": "2026-08-22 10:23:15",
  "source_ip": "10.10.10.25",
  "target_ip": "192.168.1.100",
  "initial_verdict": "疑似真实攻击",
  "confidence": 0.72,
  "evidence": [
    "检测到疑似WebShell通信",
    "攻击源与目标存在通信关系"
  ]
}
```

### 2\.2 输出（即生成的报告）

Agent 输出结构化调查结果，包括：

```Plain Text
事件基本信息
调查结论
风险等级
攻击类型
关键证据
证据来源
调查步骤
工具调用记录
攻击链/攻击过程
调查置信度
处置建议
是否需要人工接管
```



---

# 第一版最小调查流程

第一版采用单 Agent \+ 单工具的最小闭环。

```Plain Text
安全事件
   ↓
Agent接收事件
   ↓
分析已有证据
   ↓
识别证据缺口
   ↓
规划下一步调查
   ↓
调用安全工具，待探索
   ↓
获取补充证据
   ↓
更新调查结论
   ↓
判断是否满足停止条件
   ↓
输出结构化调查报告
```



**让 Agent 根据已有证据判断“还缺什么”，然后主动寻找缺失证据。并进行进一步判断**

---

# 第一版调查示例

以 **WebShell 事件**作为第一版示例场景。

### Step 1：接收事件

Agent收到：

> 高危 WebShell 告警，攻击源 `10.10.10.25`，目标 `192.168.1.100`。
> 
> 

已有证据：

```Plain Text
✓ WebShell相关告警
✓ 攻击源IP
✓ 目标IP
✓ 攻击时间
```

---

### Step 2：识别证据缺口

Agent分析后发现：

```Plain Text
缺少：
① 目标IP对应的资产信息
② 目标资产重要程度
③ 是否属于关键服务器
```

于是形成调查计划：

> **查询目标资产信息。**
> 
> 

---

### Step 3：调用调查工具

第一版至少接通一种真实平台能力，因此优先设计为：

> **XDR事件/资产相关查询能力**
> 
> 

如果比赛环境当前还没有完成该接口联调，则第一版开发阶段使用 Mock 保证流程可运行，但**最终 MVP 必须将至少一个工具替换为真实平台调用**。

例如：

```Plain Text
Agent
 ↓
query_asset(192.168.1.100)
 ↓
XDR
 ↓
返回资产信息
```

深信服 XDR 官方资料确认其具备多源安全数据聚合、事件调查及开放接口能力；官方事件检索也支持按照事件等级、来源、GPT研判结论、事件定性、数据源和处置状态等条件检索。\(深信服技术支持\)

---

### Step 4：根据工具结果更新结论

例如返回：

```Plain Text
资产名称：OA服务器
资产类型：Web服务器
资产重要等级：高
```

Agent更新判断：

> 目标为高价值业务服务器，原有 WebShell 告警的风险进一步提升。
> 
> 

调查置信度：

```Plain Text
0.72 → 0.88
```

---

### Step 5：输出调查报告

例如：

```Plain Text
调查结论：
高度疑似真实WebShell攻击

风险等级：
HIGH

关键证据：
1. XDR检测到WebShell相关行为
2. 攻击源与目标存在异常通信
3. 目标资产为高重要性OA服务器

攻击过程：
攻击源
 ↓
Web攻击
 ↓
OA服务器
 ↓
疑似WebShell通信

处置建议：
1. 对攻击源进行阻断
2. 对目标服务器进行进一步终端调查
3. 检查WebShell文件及相关进程

调查置信度：
88%
```

---

# 深信服平台能力接入设计





---

# 安全GPT在 Agent 中的定位

作为某个节点



- 安全事件解读

- 安全告警解读

- 威胁实体调查

- 近期高频告警调查

- 相似告警调查

- 威胁态势调查

- 同源同目的告警调查

并支持对事件进行攻击定性和处置建议分析。\(深信服技术支持\)

因此后续可以设计：

```Plain Text
深度调查 Agent
       ↓
发现需要专业判断
       ↓
调用安全GPT
       ↓
获得分析结果
       ↓
Agent结合其他证据
       ↓
更新最终结论
```

这样才能体现**Agent的自主调查能力**。

---

# 调查过程与状态记录

为了满足“调查过程必须可追踪”的要求，Agent需要保存每一步状态。

记录为：

```Plain Text
step_id
事件ID
当前状态
调查目标
证据缺口
调用工具
工具输入
工具输出
新增证据
结论变化
下一步计划
时间戳
```

例如：

```Plain Text
Step 1
状态：分析中
发现证据缺口：目标资产信息

Step 2
状态：工具调用
工具：query_asset
输入：192.168.1.100

Step 3
状态：证据更新
新增证据：高重要性OA服务器

Step 4
状态：结论更新
疑似攻击 → 高度疑似真实攻击
```

这样前端就可以直接展示 Agent 的调查轨迹。

---

# 停止条件与人工接管



MVP实际只跑：

```Plain Text
事件分析
 ↓
证据缺口
 ↓
工具调用
 ↓
结论更新
 ↓
报告输出
```

停止条件：

满足以下任意条件即可结束：

### 条件一：证据足够

已经能够支持明确调查结论。

### 条件二：达到最大步骤

```Plain Text
step >= 5
```

停止继续调用工具。

### 条件三：工具无法获得数据

例如：

```Plain Text
XDR查询失败
数据为空
权限不足
```

Agent不能自行编造结果。

应输出：

**证据不足，需要人工接管。**

---

## 8\.3 人工接管条件

以下情况触发人工接管：

```Plain Text
高风险事件但证据不足
+
关键工具调用失败

或者

调查结果存在明显冲突

或者

涉及高风险处置动作
```

高风险事件但证据不足、关键证据调用失败、结果与输入有强烈冲突，涉及高风险操作

---

# 第一版 MVP 架构

建议采用下面的结构：

```Plain Text
深信服 XDR
                        │
              ┌─────────┴─────────┐
              │                   │
          真实数据/API          安全GPT
              │                   │
              └─────────┬─────────┘
                        ↓
                深度调查 Agent
                        │
              ┌─────────┴─────────┐
              ↓                   ↓
          证据管理器            工具调用器
              │                   │
              ↓                   ↓
          调查状态记录        OpenAPI/MCP
              │                   │
              └─────────┬─────────┘
                        ↓
                  调查报告生成
                        ↓
                 结构化调查结果
```

第一版开发时：

```Plain Text
真实 XDR能力
      +
Mock工具
      +
Agent
```

最终逐步把 Mock 替换成真实平台工具。

---

# 当前依赖



1. XDR OpenAPI具体接口

2. API认证方式

3. MCP工具清单及参数。或者是其他低代码工具、相关安全工具

4. XDR事件数据、格式

5. 安全GPT调用方式/权限

（就是缺

当前开放哪些 XDR OpenAPI / MCP Tool。

XDR返回的事件、告警、资产数据具体字段是什么）

---

# 实现结构（对齐 sec_agent.deep_agent 代码）

第一版实现落地为 `sec_agent.deep_agent` 子包，模块与设计对应关系：

| 设计环节 | 代码位置 |
|----------|----------|
| 输入（`SecurityEventInput`） | `src/sec_agent/deep_agent/models.py` |
| 输出（`InvestigationReport`） | `src/sec_agent/deep_agent/models.py` |
| 调查闭环 / 停止条件 / 人工接管 | `src/sec_agent/deep_agent/agent.py`（`SYSTEM_PROMPT` + `investigate`） |
| 工具抽象与注册 | `src/sec_agent/deep_agent/tools/base.py` |
| 真实 MCP 工具 | `src/sec_agent/deep_agent/tools/mcp_client.py` |
| Mock 工具（MVP 兜底） | `src/sec_agent/deep_agent/tools/mock.py` |
| LLM 驱动 | `src/sec_agent/deep_agent/llm.py` |
| 命令行入口 | `src/sec_agent/deep_agent/main.py` |

安全边界在代码中的落点：

- 不直接推进业务状态：工具均为只读查询，处置建议仅作为报告字段输出，不自动执行。
- 不直接绕过工具适配层调用真实平台：统一走 `Tool` / `MCPClient` 抽象。
- 不执行高风险处置动作：无阻断、隔离、删除等动作实现。

## 工具名与内部别名（LLM 兼容层）

### 背景

深信服 MCP 服务返回的真实工具函数名含中文（如 `cybersec_攻击状态检测`），而 OpenAI 兼容接口（DeepSeek / OpenAI 等）**强制函数名匹配 `^[a-zA-Z0-9_-]+$`**（仅允许英文字母、数字、下划线、中划线）。若把中文名直接作为 function schema 发给 LLM，接口会返回：

```
400 Invalid 'tools[10].function.name': string does not match pattern '^[a-zA-Z0-9_-]+$'
```

### 设计：内部别名层

在工具注册表与 LLM 之间加一层别名翻译，对 LLM 完全透明：

```
深信服 MCP 工具（真实中文函数名）
        │  register 时按 ALIAS_MAP 映射
        ▼
ToolRegistry 内部别名（ASCII，如 cybersec_attack_status_detect）
        │  schemas() 发别名给 LLM
        ▼
LLM 自主调用（只看到 ASCII 别名）
        │  resolve() 解析回真实名
        ▼
真实 MCP 调用执行（工具调用记录留痕真实名）
```

- 发 schema：`ToolRegistry.schemas()` 使用 `_aliases[真实名]` 作为 `function.name`。
- 执行调用：`agent.py` 收到 LLM 返回的别名后，先 `tools.resolve(别名)` 还原为真实名，再 `tools.call(真实名, params)` 执行；审计留痕记录真实名。
- 规则：ASCII 工具名（Mock 与 `vuln_*` 等）别名＝真实名，无需映射；未收录在 `ALIAS_MAP` 的未来中文工具，由 `_auto_alias()` 自动生成去重 ASCII 别名兜底。

代码位置：`src/sec_agent/deep_agent/tools/base.py`（`ALIAS_MAP`、`_auto_alias`、`ToolRegistry.resolve / alias_of / schemas`）、`src/sec_agent/deep_agent/agent.py`（调用前 resolve）。

### 工具与「内部别名」映射关系表

| 真实工具名（深信服 MCP） | 内部别名（发给 LLM） | 所属 MCP 服务 |
|--------------------------|----------------------|---------------|
| `cybersec_攻击状态检测` | `cybersec_attack_status_detect` | 检测大模型 |
| `cybersec_攻击类型检测` | `cybersec_attack_type_detect` | 检测大模型 |
| `incidents_安全事件相关的查询和统计` | `incidents_query_statistics` | 网络安全数据查询 |
| `alerts_安全告警相关的查询和统计` | `alerts_query_statistics` | 网络安全数据查询 |
| `vul_漏洞相关的查询和统计` | `vul_query_statistics` | 网络安全数据查询 |
| `vul_弱密码相关的查询和统计` | `vul_weak_password_query` | 网络安全数据查询 |
| `vul_资产关联漏洞数据查询` | `vul_asset_related_query` | 网络安全数据查询 |
| `assets_资产相关的查询和统计` | `assets_query_statistics` | 网络安全数据查询 |
| `secgpt_告警事件解读研判` | `secgpt_alert_interpretation` | 运营大模型 |
| `secgpt_威胁实体的调查分析` | `secgpt_threat_entity_analysis` | 运营大模型 |
| `dbproxy_事件数据查询工具` | `dbproxy_event_query` | 自由数据查询 |
| `dbproxy_告警数据查询工具` | `dbproxy_alert_query` | 自由数据查询 |
| `dbproxy_脆弱性数据查询工具` | `dbproxy_vulnerability_query` | 自由数据查询 |
| `dbproxy_资产数据查询工具` | `dbproxy_asset_query` | 自由数据查询 |
| `dbproxy_威胁实体数据查询工具` | `dbproxy_threat_entity_query` | 自由数据查询 |

> 其余工具（Mock 6 个 + 漏洞信息查询 `vuln_*` 4 个）函数名本已是 ASCII，别名＝真实名，不列入上表。映射表与代码中 `ALIAS_MAP` 保持一致，若深信服侧函数名调整需同步更新两处。

主链接入方式见 `development.md` 的「与主链集成状态」。

---

# 复验结果（2026-08-25 实测）

复验对象：最新 main（含 PR #13「深度调查 Agent 子智能体」，2026-08-24 合并）可真实加载 `sec_agent.deep_agent`；并对 feature 分支（275e0ec，含主链桥接）做了主链实际运行路径实测。按实际情况记录，分「独立运行」与「主链」两条路径。

## ① 独立运行路径（`python -m sec_agent.deep_agent.main`）— 复验通过

- **Agent 加载**：`import sec_agent.deep_agent` 成功，加载的即 PR #13 的 `agent.DeepInvestigationAgent`（可实例化）。
- **工具调用**：`TOOL_MODE=mock` 可用 6 个 Mock 工具；本轮完整调查实际发生 **7 次工具调用**（`query_asset`×2、`query_alerts`×2、`query_vulnerabilities`、`vuln_intelligence`、`secgpt_analyze`；其中 2 次 `failed`=数据不可得），记录于 `report.json.tool_call_records`。
- **结构化报告**：生成完整报告（结论=确认真实 WebShell 攻击、风险 HIGH、证据 6 条、调查步骤 3 步、工具记录 7 条、攻击链闭环、置信度 0.86、处置建议 6 条、人工接管标记、未解决问题 5 项）。
- **LLM**：本轮**实际调用 LLM**（结构化报告与步骤叙述只能由 LLM ReAct 闭环产生；LLM 未配置时 agent 直接报错）。
- **内部 fallback**：本轮**未发生**（结论为具体判定而非「证据不足」）。`need_manual_takeover=true` 是正常业务标记（高风险处置需人工确认），不等于 fallback。
- **测试**：`tests/test_investigation_agent.py` 16 passed / 1 skipped。

## ② 主链路径（feature 275e0ec）— 桥接已修复（2026-08-25）

- 主链 `Orchestrator` INVESTIGATING 阶段支持 3 个后端（`INVESTIGATION_BACKEND`：`auto` 默认 / `deep_agent` / `tool_mock`），由 `services/investigation.py` + `services/deep_agent_bridge.py` 实现。
- **修复**：bridge 原以 `importlib.import_module("deep_agent.*")` 导入不存在的顶层包 → `auto` 恒回退内部子链；已按方案 A 改为 `sec_agent.deep_agent.*`，并补回归测试（`test_bridge_loads_real_deep_agent_modules`）。
- **修复后实测**（`auto` 后端，`TOOL_MODE=mock`，配置 LLM）：bridge **真实加载 PR #13 Agent、实际调用 LLM**，跑 **7 次 Mock 工具调用**，输出完整结构化报告（结论=确认真实 WebShell 攻击 / 5 步调查 / 置信度 0.88 / 处置建议 6 条），**未发生内部 fallback**。
- **行为变化（如实记录）**：WebShell 样例下 deep_agent 报告标记人工接管（`need_manual_takeover=true`，因处置涉及隔离/下线高风险动作 + 源 IP 等取证数据缺口）→ 主链在 INVESTIGATING 后转入 **HUMAN_REQUIRED**（修复前回退子链会直接走自动处置至 COMPLETED）。这是完整 Agent 的保守行为，符合「高风险处置需人工确认」设计，非缺陷。
- main（7db2724）基线：无 bridge、无 `deep_agent` 引用，仅占位单步查询（grep 确认）。

---

# 实现层次区分

| 层次 | 内容 | 当前状态 |
|------|------|----------|
| **本地 Python 实现** | `sec_agent.deep_agent` 完整调查闭环（LLM 驱动 + 工具 + 结构化报告） | ✅ 独立运行复验通过；主链 bridge 已修复并实测接入 |
| **FastGPT 目标路线** | 将调查逻辑迁移到 FastGPT 编排（深信服 MCP 工具已由 FastGPT 托管） | 🔶 目标规划，未实现 / 未验证 |
| **Mock 工具** | 6 个内置兜底工具（人工构造数据） | ✅ 本轮复验使用；仅覆盖 WebShell 主场景 |
| **真实平台能力** | 深信服 MCP 5 服务 19 工具、真实 XDR 数据 | 🔶 已连通（dbproxy 实测成功）；整体联调待客服确认，本轮未使用 |







