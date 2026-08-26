# 深度调查 Agent 模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 深度调查 Agent（`sec_agent.deep_agent` 子智能体） |
| 负责人 | 杨景凡（T0826-03 复验与文档）；实现与知识包内容见变更记录 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验（独立运行与主链 bridge 均已实测） |
| 能力性质 | `自研代码`（LLM 驱动调查闭环 + 工具层 + 知识包检索）/ `真实平台`（LLM 真实调用、dbproxy 等 MCP 真实连通）/ `Mock`（6 个兜底工具 + 知识包为人工构造演示）/ `fallback`（`auto` 后端 bridge 不可用时回退内部子链）。各能力实际范围见「实现层次区分」 |
| 关联任务/需求 | T0826-03：调查 Agent 复验和调查文档；PR #13：深度调查 Agent 子智能体 |
| 关联正式交付章节 | 《系统设计说明书》风险研判设计的调查延伸；正式交付章节编号待定（见「当前限制与后续事项」） |
| 对应PR或Commit | PR #13（子智能体）；`383fec7`（bridge 双包名修复）；`3c49db2`（报告时间戳）；本次 T0826-03 提交（知识包检索工具 + 文档完善） |
| 最后更新时间 | 2026-08-26 |
| 最后复验时间 | 2026-08-26 |

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
| 知识包 md 文件入库（`deep_agent/knowledge/webshell_min.md`） | Agent 运行资源需随仓库分发、可追溯 | 运行时读外部路径（不可移植） |
| 三后端（`auto` / `deep_agent` / `tool_mock`） | 真实 Agent、仅桥接、仅内部子链三种运行模式按需选择 | 单后端（无法区分真实/回退路径） |
| `max_tool_calls=12` 硬上限（可环境变量 `AGENT_MAX_TOOL_CALLS` 覆盖） | 防 LLM 死循环、控制单次调查成本；8 次实测偏紧（LLM 常耗尽步数未收尾而降级），扩到 12 并接近上限注入收尾提醒 | 无限循环（不可控）；步数过紧（原 8 次） |

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
| dbproxy 等真实 MCP 查询本轮返回合法空集（样例虚构实体在真实库无命中） | 不阻塞（工具链路真实连通） | 真实平台事件数据接入后复验 |
| Windows Python 缺 `tzdata` 时主链 import 报 `ZoneInfoNotFoundError` | 阻塞主链 | 需 `pip install tzdata`（本机已装；依赖清单待补） |
| 正式交付章节编号未对齐《系统设计说明书》 | 待确认 | 后续对齐章节编号 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-24 | PR #13 | 深度调查 Agent 子智能体落地 `sec_agent.deep_agent` | 是 |
| 2026-08-25 | `383fec7` | bridge 双包名修复（`deep_agent` / `sec_agent.deep_agent`），补回归测试 | 是 |
| 2026-08-25 | `3c49db2` | `-o` 报告名自动加时间戳，不覆盖旧报告 | 是 |
| 2026-08-26 | 随本次 T0826-03 提交 | 新增 `knowledge_query` 知识包检索工具（`tools/knowledge.py` + `knowledge/webshell_min.md`），CLI 与主链 bridge 注册 | 是（单测与检索验证通过，真实 LLM 轮待跑） |
| 2026-08-26 | 本次（方案 C 提交） | 步数上限 `max_tool_calls` 8→12（可 `AGENT_MAX_TOOL_CALLS` 覆盖）；接近上限注入收尾提醒；降级报告提炼已采证据与知识包引用 | 是（47 passed / 1 skipped） |

---

## 附录 A：实现层次区分

| 层次 | 内容 | 当前状态 |
|------|------|----------|
| **本地 Python 实现** | `sec_agent.deep_agent` 完整调查闭环（LLM 驱动 + 工具 + 结构化报告 + 知识包检索），`auto` 后端经 bridge 接入主链 | ✅ 独立运行与主链均复验通过（2026-08-25/26） |
| **FastGPT 目标路线** | 将调查逻辑迁移到 FastGPT 编排（深信服 MCP 已由 FastGPT 托管） | 🔶 目标规划，未实现 / 未验证 |
| **Mock 工具** | 6 个内置兜底工具 + 知识包条目（人工构造演示数据） | ✅ 本轮复验使用；仅覆盖 WebShell 主场景 |
| **真实平台能力** | LLM（DeepSeek OpenAI 兼容）真实调用；深信服 MCP 5 服务 19 工具真实连通 | 🔶 LLM 已实测；dbproxy 查询实测返回合法空集（样例虚构实体无命中），真实数据联调待客服/平台确认 |

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
