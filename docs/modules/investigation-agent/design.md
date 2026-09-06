# 深度调查 Agent 模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 深度调查 Agent（`sec_agent.deep_agent` 子智能体） |
| 负责人 | 杨景凡（T0826-03 复验与文档；T0903-03 运行 B 与收口）；实现与知识包内容见变更记录 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验（独立运行与主链 bridge 均已实测；真实 XDR 数据经运行 B 复验，见变更记录） |
| 能力性质 | `自研代码`（LLM 驱动调查闭环 + 工具层 + 知识包检索 + 证据守卫）/ `真实平台`（LLM 真实调用、dbproxy 等 MCP 真实连通且真实数据已复验）/ `Mock`（6 个兜底工具 + 知识包为人工构造演示）/ `fallback`（`auto` 后端 bridge 不可用时回退内部子链）。各能力实际范围见「实现层次区分」 |
| 关联任务/需求 | T0826-03：调查 Agent 复验和调查文档；T0903-03：运行 B、PR 31 与调查 Agent 收口；PR #13：深度调查 Agent 子智能体 |
| 关联正式交付章节 | 《系统设计说明书》风险研判设计的调查延伸；正式交付章节编号待定（见「当前限制与后续事项」） |
| 对应PR或Commit | PR #13（子智能体）；`383fec7`（bridge 双包名修复）；`3c49db2`（报告时间戳）；PR #31（MCP 空结果识别：空 text→partial，已合并）；PR #36（证据守卫，待合并）；T0903-06 字段契约（陈敏，`docs/modules/platform-tools/xdr_field_mapping.csv` 等） |
| 最后更新时间 | 2026-09-04 |
| 最后复验时间 | 2026-09-04（真实 XDR 数据 + 真实 MCP，运行 B） |

## 1. 目标与非目标

### 1.1 目标

- 对**高风险、疑似真实攻击或现有证据不足**的安全事件，在风险研判基础上开展自动化深度调查：主动识别证据缺口 → 调用工具补证 → 更新结论与置信度 → 输出结构化调查报告。
- **知识包驱动**：Agent 可通过 `knowledge_query`（语义等价 `knowledge.query`）按关键词检索内置《最小 WebShell 知识包》，获得攻击原理 / 攻击特征 / 管理工具流量特征 / 证据检查清单 / 处置建议模板，返回 `evidence_refs` 直接填入调查报告。
- 与主链 `Orchestrator` 集成：`INVESTIGATING` 阶段经 `DeepAgentBridge` 桥接，支持 `auto` / `deep_agent` / `tool_mock` 三后端。

### 1.2 非目标

- **不推进业务状态**：调查为只读，不直接修改事件状态机。
- **不执行高风险处置动作**：阻断 / 隔离 / 删除 / 终止进程等仅作为报告中的处置建议字段输出，执行需下游审批与平台权限。
- **FastGPT 目标路线**（将调查逻辑迁移到 FastGPT 编排）本阶段**不实现**，仅作为后续规划（见「实现层次区分」）。

## 2. 职责与边界

- 本模块负责：调查闭环（接收事件 → 分析证据 → 识别缺口 → 规划步骤 → 调用工具 → 更新结论 → 判断停止 → 输出报告）；工具注册与调用（Mock / 知识包 / MCP）；知识包解析与检索。
- 本模块不负责：告警接入 / 关联 / 风险研判（上游 `ingest` / `correlation` / `triage`）；处置执行与验证（下游 `response` 系列）；业务状态推进（`StateMachine`）。
- 需要人工参与的环节：调查证据不足 / 关键工具失败 → 输出「证据不足，需要人工接管」；高风险处置动作 → 下游审批环节。

## 3. 输入与输出

### 3.1 输入

`SecurityEventInput`（`deep_agent/models.py`），由 bridge 从上游 `SecurityEvent + TriageResult` 转换而来。

| 字段/对象 | 类型 | 必填 | 来源 | 含义与约束 |
|---|---|---|---|---|
| `event_id` | str | 是 | 上游 ingest | 事件 ID |
| `event_type` | str | 是 | 上游 | 事件类型，如 WebShell |
| `severity` | str | 是 | 上游 triage | 风险等级 HIGH/MEDIUM/LOW |
| `timestamp` | str | 是 | 上游 | 事件时间 |
| `source_ip` / `target_ip` | str | 是 | 上游 | 攻击源 / 目标资产 |
| `alerts` | list[str] | 是 | 上游 | 已有告警 |
| `evidence` | list[str] | 是 | 上游 | 已有证据 |
| `initial_verdict` | str | 是 | 上游 triage | 初步风险研判 |
| `confidence` | float | 是 | 上游 triage | 研判置信度 0~1 |
| `triage` | dict | 否 | 上游 triage | 完整研判结果（真实性/风险分/证据缺口） |
| `trace_id` / `run_id` | str | 否 | orchestrator | 全链路追踪编号 |

输入 JSON 示例（上游传入）：

```json
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

### 3.2 输出

`InvestigationReport`（`deep_agent/models.py`），经 bridge 转为主链 `InvestigationReport` 领域模型。

| 字段/对象 | 类型 | 去向 | 含义与约束 |
|---|---|---|---|
| `conclusion` / `risk_level` / `attack_type` | str | 下游决策/报告 | 调查结论、风险等级、攻击类型 |
| `key_evidence` / `evidence_source` | list[str] | 下游决策/报告 | 关键证据与来源；知识包检索到的 `evidence_refs` 可填入来源 |
| `investigation_steps` / `tool_call_records` | list | 报告/审计 | 调查步骤与工具调用记录（代码侧真实采集，可审计） |
| `attack_chain` | str | 报告 | 攻击链 / 攻击过程 |
| `confidence` | float | 下游决策 | 调查置信度 0~1 |
| `disposal_suggestions` | list[str] | 下游决策 | 处置建议（不自动执行） |
| `need_manual_takeover` / `manual_takeover_reason` | bool/str | 主链状态 | 是否人工接管及原因 |
| `unresolved_issues` / `affected_objects` | list[str] | 报告 | 未解决问题 / 涉及对象 |

## 4. 核心流程与状态变化

调查闭环（ReAct 风格，`agent.py` 的 `investigate`）：

1. 接收事件（`_build_messages` 构造 system + user 消息）。
2. LLM 推理：分析已有证据 → 识别证据缺口 → 规划下一步（可能触发工具调用）。
3. 若 LLM 请求工具：`resolve()` 还原真实工具名 → `call()` 执行 → 记录 `tool_call_records` → 结果回填对话，循环；`knowledge_query` 命中的 `evidence_refs` 结构化保留在调用记录中。
4. 接近上限（剩余 ≤2 次）时注入收尾提醒，促使 LLM 及时输出报告（避免耗尽步数降级）。
5. 停止条件（满足任一即输出报告）：证据足够 / 达到最大步数（`max_tool_calls=12` 硬上限） / 工具无法获得数据。
6. 输出结构化报告（`_parse_report` 严格 JSON）；解析失败或超步数 → `_fallback_report`（证据不足 → 人工接管，且尽力提炼已采集的工具证据与知识包引用写入报告）。

主链状态影响：`INVESTIGATING` →（`needs_human=false` 且有处置方案）→ `DECISION_READY` →（高风险）→ `APPROVAL_REQUIRED`；`needs_human=true` → `HUMAN_REQUIRED`。本模块自身不直接修改状态机，状态迁移由 `Orchestrator` 驱动。

异常路径：LLM 未配置 → 抛错（主链 bridge 视后端回退或置 `_unavailable_report`）；报告解析失败 → `_fallback_report`；工具调用异常 → `ToolRegistry.call` 兜底返回 `failed`。

## 5. 上下游关系与契约

| 方向 | 模块/接口 | 契约或文档位置 | 当前状态 |
|---|---|---|---|
| 上游 | `services/orchestrator.py` → `services/investigation.py` | `DeepInvestigationAgent.investigate(trace_id, event, triage, run_id)` | 已对齐 |
| 上游 | `services/deep_agent_bridge.py`（`auto`/`deep_agent` 后端） | 桥接 `sec_agent.deep_agent`，领域模型互转 | 已对齐（`383fec7` 双包名修复） |
| 下游 | `services/response.py` `ResponseDecisionService.build_plan` | 消费 `InvestigationReport`（`needs_human` / `recommended_actions` / `affected_objects`） | 已对齐 |
| 内部 | `tools/mock.py` / `tools/knowledge.py` / `tools/mcp_client.py` | 统一 `Tool` + `ToolRegistry` 契约 | 已对齐 |

## 6. 安全边界

- 权限与审批：调查只读；处置建议不自动执行；高风险处置由下游 `APPROVAL_REQUIRED` 审批。
- 输入校验：`SecurityEventInput.from_dict` 过滤未知字段；LLM 返回严格 JSON 解析，失败走 `_fallback_report`，不编造证据。
- **证据守卫（evidence guard，PR #36，待合并）**：解析报告时若没有任何真实 `success`/`partial` 工具调用记录，拒绝接受 LLM 生成的调查步骤与结论，直接走 `_fallback_report`（证据不足→人工接管）；即使存在成功记录，`investigation_steps` 也只能引用代码侧真实执行过的工具（真实名 + ASCII 别名双匹配），防止 LLM 虚构工具调用步骤。`_fallback_report` 与守卫对 `partial`（合法空集）语义一致——空集不算「无记录」。
- 敏感信息处理：LLM API Key / 真实 MCP URL 只从环境变量或 gitignore 的本地文件（`llm_config.local.json` / `mcp_servers.local.json`）读取，不入代码、不入文档、不入样例。
- 失败、超时与人工接管：LLM 超时/异常 → bridge 依后端回退内部子链或置不可用报告；证据不足 → 人工接管标记。
- 真实执行与 Mock 边界：见「实现层次区分」与 `development.md` 第 7 节边界表；LLM 调用、MCP 查询均为真实执行（本轮已实测），Mock 仅作为工具数据兜底。

## 7. 关键设计决策

| 决策 | 原因 | 未采用方案及原因 |
|---|---|---|
| 内部别名层（`ALIAS_MAP` + `_auto_alias`） | OpenAI 兼容接口强制函数名 `^[a-zA-Z0-9_-]+$`，深信服 MCP 中文函数名直接发送会 400 | 直接发中文名（实测 400，不可行） |
| bridge 双包名兼容（`deep_agent` / `sec_agent.deep_agent`） | 包位置在合并中反复变化，避免导入路径耦合 | 硬编码单包名（曾导致 `auto` 恒回退内部子链） |
| 报告文件名自动加时间戳（`-o`） | 避免重复运行覆盖旧报告 | 固定文件名（会覆盖） |
| 知识包检索工具代码名 `knowledge_query` | 函数名不允许 `.`，`knowledge.query` 非法 | 直接用 `knowledge.query`（OpenAI 拒绝） |
| 知识包统一读沈洪旭权威版（`src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`） | 避免与 PR #8（沈洪旭知识包交付）建立第二套知识入口；运行资源随仓库分发、可追溯 | 各自维护一份副本（重复知识源，已废弃 `webshell_min.md`） |
| 三后端（`auto` / `deep_agent` / `tool_mock`） | 真实 Agent、仅桥接、仅内部子链三种运行模式按需选择 | 单后端（无法区分真实/回退路径） |
| `max_tool_calls=12` 硬上限（可环境变量 `AGENT_MAX_TOOL_CALLS` 覆盖） | 防 LLM 死循环、控制单次调查成本；8 次实测偏紧（LLM 常耗尽步数未收尾而降级），扩到 12 并接近上限注入收尾提醒 | 无限循环（不可控）；步数过紧（原 8 次） |
| **证据守卫**：零真实成功/部分成功工具记录时拒绝 LLM 未验证结论（PR #36） | LLM 可能在 MCP 全挂/超时/鉴权失败时虚构「已调用工具并返回证据」；工具调用记录由代码侧采集，必须以此为准 | 信任 LLM 自述（会把虚构步骤写进正式报告，违背「绝不编造证据」） |
| `investigation_steps` 只保留真实执行过工具的步骤（真实名 + ASCII 别名双匹配） | LLM 看到的是 ASCII 内部别名、代码记录的是 resolve 后的真实中文名，仅比对一个会误过滤全部步骤 | 只比真实名（PR #30 初版做法，别名不一致导致 `steps` 恒为空） |

## 8. 非功能、可观测与审计要求

| 维度 | 当前要求或设计 | 验证方式 |
|---|---|---|
| 性能与时延 | 单轮调查受 LLM 网络与调用次数影响（实测约数十秒）；工具调用有 `timeout_seconds` | `--list-tools` 秒级；完整调查计时 |
| 稳定性与可重复性 | Mock 工具数据固定可复现；知识包解析确定性 | `tests/test_knowledge_tool.py`、`test_investigation_agent.py` 稳定通过 |
| 可观测性 | `tool_call_records` 由代码真实采集（工具名/输入/输出/状态）；`investigation_steps` 记录步骤；`--list-tools` 列工具 | 报告 JSON 字段、CLI 输出 |
| 审计与追踪 | `trace_id` / `run_id` 贯穿主链；工具调用留痕真实名（非内部别名） | `GET /events/{id}/timeline`、报告字段 |

## 9. 当前限制与后续事项

| 限制或未实现项 | 对主链影响 | 后续条件/负责人 |
|---|---|---|
| FastGPT 编排迁移（目标路线） | 不阻塞（本地实现已可用） | 待 FastGPT 编排能力确认 |
| 知识包为最小集：问答样本 2（攻击组织）、样本 3（DET0394 细节）未覆盖 | 不阻塞 | 扩充知识包章节即可提升检索覆盖 |
| ~~dbproxy 等真实 MCP 查询返回合法空集待真实数据复验~~ → **已复验**：运行 B（2026-09-02，真实 XDR 告警）12 次真实 MCP 调用命中真实告警/资产/漏洞/事件数据，5 次返回数据、3 次合法空集；因 secgpt 研判 500 + 部分查询失败证据不足，合规进入 `HUMAN_REQUIRED` | 不阻塞 | 复验通过（见 test.md §6.2） |
| **非 dbproxy 工具的错误文本被误标 `success`**（`Input validation error`、`Cannot do exclusion`、secgpt `HTTP 500` 等） | 可能被证据守卫误当有效记录放行 | PR #36 收口的 M4，单独提 commit 修 `_to_tool_result`（顺序 4 待办） |
| **证据守卫（PR #36）尚未合入 main** | 合并前「虚构步骤入报告」仍有敞口 | PR #36 合并（含删第 214 行空白行） |
| **主链 `InvestigationReport` 的 `key_evidence_refs` 语义未统一**：`deep_agent` 后端把 LLM 自由文本证据塞入 refs，`tool_mock` 后端填 `{alert_id}:traceBackId:{id}` 格式 ref_id | 报告证据引用格式不统一，与 T0903-06 字段契约 §6 不一致 | 桥接层分离 key_evidence（正文）与 key_evidence_refs（ref_id），见交接确认 |
| Windows Python 缺 `tzdata` 时主链 import 报 `ZoneInfoNotFoundError` | 阻塞主链 | 需 `pip install tzdata`（本机已装；依赖清单待补） |
| 正式交付章节编号未对齐《系统设计说明书》 | 待确认 | 后续对齐章节编号 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-24 | PR #13 | 深度调查 Agent 子智能体落地 `sec_agent.deep_agent` | 是 |
| 2026-08-25 | `383fec7` | bridge 双包名修复（`deep_agent` / `sec_agent.deep_agent`），补回归测试 | 是 |
| 2026-08-25 | `3c49db2` | `-o` 报告名自动加时间戳，不覆盖旧报告 | 是 |
| 2026-08-26 | 随本次 T0826-03 提交 | 新增 `knowledge_query` 知识包检索工具（`tools/knowledge.py` + 知识包），CLI 与主链 bridge 注册 | 是（单测与检索验证通过，真实 LLM 轮待跑） |
| 2026-08-27 | 本次 T0827-03 提交 | 知识源统一：`knowledge_query` 改读沈洪旭权威版 `src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`，删除本地副本 `webshell_min.md`，「Agent 输入输出约定」章节迁至本文第 3 节 | 是 |
| 2026-08-27 | 本次（打包修复） | 知识包迁入 `sec_agent.deep_agent` 包内并声明 `[tool.setuptools.package-data]`，`knowledge.py` 改用 `importlib.resources` 读取（`pip install` 后仍可用）；`-o` 报告时间戳改微秒级 + 存在检测唯一序号 | 是（打包回归测试新增） |
| 2026-08-26 | 本次（方案 C 提交） | 步数上限 `max_tool_calls` 8→12（可 `AGENT_MAX_TOOL_CALLS` 覆盖）；接近上限注入收尾提醒；降级报告提炼已采证据与知识包引用 | 是（47 passed / 1 skipped） |
| 2026-08-28 | PR #31（已合并） | MCP 空结果识别：非 dbproxy 契约工具返回**空 text**（如 `vul_资产关联漏洞数据查询` 命中不到）也应视为「成功但无数据」→ `partial`，避免 Agent 把「无数据」当「出错」；修正 `.env.example` MCP 变量名 | 是（`test_mcp_client.py` 13 passed） |
| 2026-09-03 | PR #36（待合并，head `a4482bf`） | 证据守卫：零真实 success/partial 工具记录时拒绝 LLM 未验证结论直接 `_fallback_report`；`investigation_steps` 只保留真实执行过工具（真实名+ASCII 别名双匹配）的步骤；`_fallback_report` 统一认 `partial`；新增 `test_deep_agent_evidence_guard.py` 5 用例 | 是（evidence guard 5 passed；bridge+agent 28 passed/1 skipped） |
| 2026-09-04 | T0903-03 运行 B（服务器实测） | 真实 XDR 告警入主链（`xdr_openapi`，无回退）→ `deep_agent`+`DEEP_AGENT_TOOL_MODE=mcp` → 12 次真实 MCP 调用命中真实告警/资产/漏洞/事件数据；因 secgpt 500 + 部分查询失败证据不足进入 `HUMAN_REQUIRED` | 是（真实工具返回真正影响证据与结论） |
| 2026-09-04 | T0903-03 知识案例验证 | 加载 PR #37 case1/2/6，确认 `knowledge_query` 调用→命中→evidence_refs 入报告三链全通；case6 暴露「供应链/插件投毒无独立知识条目」缺口 | 是（3 案例全通，见反馈记录） |
| 2026-09-04 | T0903-06 字段契约对齐（陈敏） | 确认实体权威来源 `SecurityEvent.entities`（src_ips/dst_ips/assets/source_devices）+ `alert_refs` 锚定、`event_id` 不用于 XDR 查询、脱敏边界、证据 ref_id 格式；记录 3 处调查侧消费差异（时间窗/entities 透传/refs 语义） | 部分（差异 3 项待桥接层收敛） |

---

## 附录 A：实现层次区分

| 层次 | 内容 | 当前状态 |
|------|------|----------|
| **本地 Python 实现** | `sec_agent.deep_agent` 完整调查闭环（LLM 驱动 + 工具 + 结构化报告 + 知识包检索），`auto` 后端经 bridge 接入主链 | ✅ 独立运行与主链均复验通过（2026-08-25/26） |
| **FastGPT 目标路线** | 将调查逻辑迁移到 FastGPT 编排（深信服 MCP 已由 FastGPT 托管） | 🔶 目标规划，未实现 / 未验证 |
| **Mock 工具** | 6 个内置兜底工具 + 知识包条目（人工构造演示数据） | ✅ 本轮复验使用；仅覆盖 WebShell 主场景 |
| **真实平台能力** | LLM（DeepSeek OpenAI 兼容）真实调用；深信服 MCP 5 服务 19 工具真实连通 | ✅ 真实数据已复验（运行 B，2026-09-02）：真实 XDR 告警命中真实库，12 次真实 MCP 调用含真实告警/资产/漏洞/事件数据；4 处工具错误文本被误标 `success` 为已知缺口（M4 待修） |

## 附录 B：工具名与内部别名映射表

深信服 MCP 中文函数名 → 发送给 LLM 的 ASCII 内部别名（`tools/base.py` `ALIAS_MAP`）：

| 真实工具名（深信服 MCP） | 内部别名（发给 LLM） | 所属 MCP 服务 |
|---|---|---|
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

> 其余工具（Mock 6 个 + 知识包 `knowledge_query` + 漏洞信息查询 `vuln_*` 4 个）函数名本已是 ASCII，别名＝真实名，不列入上表。映射表与代码 `ALIAS_MAP` 保持一致，深信服侧函数名调整需同步更新两处。
