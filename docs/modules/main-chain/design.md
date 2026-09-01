# 主链设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 负责人 | 李雨妍 |
| 文档状态 | 已补充真实 XDR 告警接入说明 |
| 实现状态 | 主链已实现；真实 XDR 告警拉取已完成一次实机验证；真实 MCP 调查和真实处置未闭环 |
| 能力性质 | 自研代码；平台接入包含 fixed_sample / jsonl_sample / xdr_openapi；处置执行和验证仍包含 Mock 能力 |
| 关联任务/需求 | 搭建最小主流程空壳、状态流转、模块接入主链、后端主链技术集成 |
| 关联正式交付章节 | docs/deliverables/system-development-and-operation-guide.md；docs/deliverables/安全智能体系统设计说明书V2.md |
| 对应PR或Commit | 当前工作区；建议提交名 `fix: align XDR OpenAPI auth and alert ingestion` |
| 最后更新时间 | 2026-08-30 |
| 最后复验时间 | 2026-08-30 |

## 1. 目标与非目标

### 1.1 目标

- 将告警接入、告警关联、风险研判、深度调查、处置决策、审批、处置执行、处置验证串成统一后端主流程。
- 通过 `EventContext` 统一承载一次安全事件处理的上下文、状态、时间线、证据、处置结果和错误信息。
- 通过 `StateMachine` 约束业务状态流转，避免业务模块绕过编排层直接修改状态。
- 通过 `ToolRequest` / `ToolResult` 统一工具调用契约，使 fixed/jsonl 平台适配器和 MVP Mock 工具可以被主链调度。
- 对外提供 HTTP 接口，支持启动主流程、查询事件、查询时间线、提交审批和查看基础指标。

### 1.2 非目标

- 本阶段不实现 XDR OpenAPI 全量接口；当前只确认告警列表 `POST /api/xdr/v1/alerts/list` 可由后端拉取并进入主链。
- 本阶段不证明真实 XDR `uuId` 可作为服务端过滤参数；后端通过分页拉取后在本地按 `uuId` 等唯一字段匹配。
- 本阶段不实现真实高风险处置动作，执行阶段当前使用 `stateful_response_mock` 类型能力。
- 本阶段不实现长流程异步队列、断点续跑和分布式任务调度。
- 本阶段不保证 deep agent 在未配置 LLM 和真实 MCP 工具服务时真实闭环运行。

## 2. 职责与边界

- 本模块负责：接收启动请求，调用各业务模块，推进状态机，保存事件上下文，处理审批入口和主流程异常。
- 本模块不负责：具体告警解析规则、真实平台 API 鉴权、LLM 推理实现、真实封禁或隔离动作、前端页面渲染。
- 需要人工参与的环节：高风险处置审批、调查证据不足时人工接管、审批拒绝后的人工处理。

## 3. 输入与输出

### 3.1 输入

| 字段/对象 | 类型 | 必填 | 来源 | 含义与约束 |
|---|---|---|---|---|
| `StartRunRequest.source` | `fixed_sample / jsonl_sample / xdr` | 是 | API 或脚本 | 指定告警来源；`source=xdr` 需配合 `PLATFORM_BACKEND=xdr_openapi` 使用 |
| `StartRunRequest.sample_id` | `str | None` | 否 | API 或脚本 | 固定样例或 JSONL 样例 ID；未提供时由适配器按默认样例处理 |
| `StartRunRequest.xdr_event_id` | `str | None` | 否 | API 或脚本 | 真实 XDR 告警唯一标识；当前按 `uuId/event_id/alert_id/uuid/id/sample_id` 本地匹配，不假设上游支持按 `uuId` 过滤 |
| `ApprovalDecision` | Pydantic 模型 | 审批阶段必填 | API 或脚本 | 包含是否同意、审批人、原因、幂等键 |
| `Settings` | Pydantic 模型 | 是 | 环境变量 / `.env` / 默认值 | 决定平台适配器、存储后端、调查后端、CORS、MySQL 等运行配置 |

### 3.2 输出

| 字段/对象 | 类型 | 去向 | 含义与约束 |
|---|---|---|---|
| `EventContext` | Pydantic 模型 | API 响应、仓储、主流程脚本 | 一次事件处理的完整上下文，包含 `trace_id`、`run_id`、`event_id`、状态、`requested_source/effective_source/fallback_source`、时间线和模块结果 |
| `TimelineEntry` | Pydantic 模型列表 | API 响应、仓储 | 记录每次状态变化及说明 |
| `SecurityEvent` | Pydantic 模型 | 风险研判、调查、API 响应 | 告警关联后的安全事件摘要 |
| `TriageResult` | Pydantic 模型 | 调查、处置决策、API 响应 | 风险研判结论、置信度、优先级和是否进入调查 |
| `InvestigationReport` | Pydantic 模型 | 处置决策、API 响应 | 深度调查结论、证据、建议动作和人工需求 |
| `ResponseResult` | Pydantic 模型 | API 响应、仓储 | 处置方案、执行结果、验证结果 |
| `ErrorRecord` | Pydantic 模型列表 | API 响应、仓储 | 记录接入、编排或工具失败信息 |

## 4. 核心流程与状态变化

1. 接收 `StartRunRequest`，生成 `trace_id`、`run_id`，调用 `AlertIngestService` 从平台适配器读取告警。
   - 当 `PLATFORM_BACKEND=xdr_openapi` 且 `source=xdr` 时，适配器调用 XDR 告警列表接口 `POST /api/xdr/v1/alerts/list`。
   - 请求体由配置生成，默认包含 `page`、`pageSize`，可选包含 `startTimestamp`。
   - 如请求携带 `xdr_event_id`，适配器在分页返回的告警集合中按唯一字段本地匹配目标告警。
2. 初始化 `EventContext`，状态为 `RECEIVED`，写入仓储。
3. 进入 `CORRELATING`，由 `AlertCorrelationService` 将多条告警压缩为安全事件。
4. 进入 `TRIAGED`，由 `RiskTriageService` 输出恶意性、风险分、优先级和是否调查。
5. 如无需调查，直接进入 `COMPLETED`；如需要调查，进入 `INVESTIGATING`。
6. `DeepInvestigationAgent` 根据配置选择 `tool_mock`、`deep_agent` 或 `auto` 后端，输出结构化调查报告。
7. 如调查需要人工，进入 `HUMAN_REQUIRED`；否则由 `ResponseDecisionService` 生成处置方案。
8. 进入 `DECISION_READY`。如方案需要审批，进入 `APPROVAL_REQUIRED`；否则直接执行。
9. 审批通过后进入 `EXECUTING`，由 `ResponseExecutionService` 调用平台工具执行处置。
10. 执行成功后进入 `VERIFYING`，由 `ResponseVerificationService` 验证结果，最终进入 `COMPLETED`、`HUMAN_REQUIRED` 或 `FAILED`。

允许的状态迁移由 `src/sec_agent/domain/state_machine.py` 定义：

| 当前状态 | 允许迁移 |
|---|---|
| `RECEIVED` | `CORRELATING`、`FAILED` |
| `CORRELATING` | `TRIAGED`、`FAILED` |
| `TRIAGED` | `INVESTIGATING`、`COMPLETED`、`HUMAN_REQUIRED`、`FAILED` |
| `INVESTIGATING` | `DECISION_READY`、`HUMAN_REQUIRED`、`FAILED` |
| `DECISION_READY` | `APPROVAL_REQUIRED`、`EXECUTING`、`HUMAN_REQUIRED`、`FAILED` |
| `APPROVAL_REQUIRED` | `EXECUTING`、`HUMAN_REQUIRED`、`FAILED` |
| `EXECUTING` | `VERIFYING`、`FAILED` |
| `VERIFYING` | `COMPLETED`、`DECISION_READY`、`HUMAN_REQUIRED`、`FAILED` |
| `COMPLETED` | 终态，不允许继续迁移 |
| `HUMAN_REQUIRED` | 终态，不允许继续迁移 |
| `FAILED` | 终态，不允许继续迁移 |

## 5. 上下游关系与契约

| 方向 | 模块/接口 | 契约或文档位置 | 当前状态 |
|---|---|---|---|
| 上游 | HTTP `POST /runs` | `src/sec_agent/api/routes/events.py`；`StartRunRequest` | 已对齐 |
| 上游 | XDR OpenAPI 告警列表 | `src/sec_agent/platforms/xdr_openapi.py`；`XdrOpenApiAdapter` | 已完成真实告警拉取实机验证 |
| 上游 | 本地主流程脚本 | `src/sec_agent/scripts/run_flow.py` | 已对齐 |
| 上游 | 平台适配器 | `src/sec_agent/platforms/base.py`；`PlatformAdapter` | 已对齐 |
| 下游 | 告警接入 | `src/sec_agent/services/ingest.py` | 已对齐 |
| 下游 | 告警关联 | `src/sec_agent/services/correlation.py` | 已对齐 |
| 下游 | 风险研判 | `src/sec_agent/services/triage.py` | 已对齐 |
| 下游 | 深度调查 | `src/sec_agent/services/investigation.py`；`src/sec_agent/services/deep_agent_bridge.py` | 已对齐 |
| 下游 | 处置闭环 | `src/sec_agent/services/response.py` | 已对齐 |
| 下游 | 事件仓储 | `src/sec_agent/repositories/base.py`；`memory.py`；`mysql.py` | 已对齐 |
| 下游 | OpenAPI 文档 | `docs/swagger/openapi.json` | 已对齐 |

## 6. 安全边界

- 权限与审批：高风险处置方案通过 `approval_required=True` 停在 `APPROVAL_REQUIRED`，必须提交 `ApprovalDecision` 后才执行。
- 输入校验：API 入参由 Pydantic 模型校验；非法状态审批由 `Orchestrator.approve()` 拒绝。
- 敏感信息处理：真实 Token、MCP URL、平台原始地址不得写入代码、样例和文档；工具参数可通过 `sensitive_param_keys` 标识敏感字段。
- XDR 鉴权：真实 XDR 使用官方 AK/SK/联动码签名方式，密钥只从环境变量或本地 `.env` 读取，不进入仓库和文档。
- 失败、超时与人工接管：接入失败会生成 `FAILED` 事件；调查证据不足、审批拒绝或验证异常可进入 `HUMAN_REQUIRED`。
- XDR 日志查询边界：`xdr_log_query` 当前是调查补充证据工具；在告警已命中时，日志接口鉴权失败不会阻断主链进入审批。
- 真实执行与Mock边界：当前处置执行和验证仍以 Mock / 样例工具为主，不代表真实平台已经完成高风险动作。

## 7. 关键设计决策

| 决策 | 原因 | 未采用方案及原因 |
|---|---|---|
| 使用 `Orchestrator` 作为唯一主链编排入口 | 保证状态推进、仓储写入和模块调用顺序集中可控 | 未让各模块自行推进状态，避免状态不一致 |
| 使用 `EventContext` 作为主链上下文 | 便于 API、仓储、测试和前端统一读取处理结果 | 未拆成多个临时对象，避免主链结果分散 |
| 使用 `StateMachine` 限制状态迁移 | 防止非法回退、跳跃和终态继续推进 | 未直接在服务中修改字符串状态，避免缺少约束 |
| 使用 `ToolRequest` / `ToolResult` 统一工具契约 | 便于 fixed/jsonl、Mock 工具和后续真实平台工具共用调度接口 | 未让不同工具返回任意 dict，避免下游解析混乱 |
| XDR 告警按列表分页拉取后本地匹配 | 目前只确认 `uuId` 是返回结果唯一标识，未证明上游支持按 `uuId` 请求过滤 | 未把 `uuId` 直接拼到上游请求体，避免依赖未确认接口行为 |
| XDR 日志查询失败不阻断已命中告警审批 | 日志接口路径和权限尚未完成实机确认，但告警本身已包含足够字段进入主链 | 未将补充日志查询作为强依赖，避免真实告警接入被未确认日志接口阻塞 |
| 保留 `memory` 和 `mysql` 两类仓储 | 本地开发可快速运行，后续可切 MySQL 持久化 | 未强制所有环境依赖 MySQL，降低本地调试门槛 |

## 8. 非功能、可观测与审计要求

| 维度 | 当前要求或设计 | 验证方式 |
|---|---|---|
| 性能与时延 | 当前主链为同步调用，适用于 MVP 样例和接口联调；暂未定义生产时延 SLA | `pytest`、`run_flow`、HTTP 接口测试 |
| 稳定性与可重复性 | fixed_sample 和 jsonl_sample 应可重复产生稳定状态线；真实 XDR 依赖上游数据窗口和联动码有效期；审批幂等键避免重复执行 | `tests/test_state_flow.py`、`tests/test_jsonl_platform.py`、`tests/test_xdr_openapi_platform.py` |
| 可观测性 | `EventContext.timeline` 记录状态变化；`errors` 记录失败阶段；`trace_id` 串联工具调用；`requested_source/effective_source/fallback_source` 区分请求来源、实际来源和降级来源 | 查询 `/events/{event_id}`、`/events/{event_id}/timeline` |
| 审计与追踪 | `trace_id`、`run_id`、`event_id`、`idempotency_key`、`ToolRequest.call_id`、`ToolResult.raw_result_ref` 支持基本追踪 | API 响应、仓储记录、测试断言 |

## 9. 当前限制与后续事项

| 限制或未实现项 | 对主链影响 | 后续条件/负责人 |
|---|---|---|
| 真实 XDR 告警列表已接入，但只完成单接口验收 | 可支持真实告警输入主链；仍不等于 XDR 全量 OpenAPI 闭环 | 继续补齐更多查询条件、错误码、字段样本和稳定性测试 |
| 真实深信服 MCP 工具未完成主链实机闭环 | 不阻塞真实告警输入；阻塞真实调查工具闭环 | 补齐 MCP 工具地址、鉴权、工具 schema 和集成测试 |
| 真实高风险处置动作未接入 | 不阻塞主链演示；阻塞生产处置能力 | 接入真实处置 API，并明确审批、回滚和审计 |
| 主链当前以同步方式执行 | 不阻塞本地和 CI；高并发或长任务场景待优化 | 引入异步任务、队列、状态持久化和重试策略 |
| MySQL 仓储需要真实数据库环境复验 | 不阻塞 memory 模式；影响持久化上线 | 准备 MySQL 环境并补充迁移、清理和回归测试 |
| XDR 日志查询接口路径和权限未确认 | 不阻塞告警输入；可能影响调查证据丰富度 | 索要真实日志查询契约并完成只读联调 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-26 | 当前工作区新增 | 新增主链模块设计文档，按现有 Orchestrator 和状态机补充内容 | 否 |
| 2026-08-30 | 当前工作区更新 | 补充真实 XDR 告警列表接入、官方签名、本地 `uuId` 匹配、日志查询非阻断和真实能力边界 | 是 |
