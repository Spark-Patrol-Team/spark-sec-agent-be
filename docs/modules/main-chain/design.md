# 主链设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 负责人 | 李雨妍 |
| 文档状态 | 草稿 |
| 实现状态 | 已实现未复验 |
| 能力性质 | 自研代码；当前平台接入、处置执行和验证包含 Mock / fixed_sample / jsonl_sample 能力 |
| 关联任务/需求 | 搭建最小主流程空壳、状态流转、模块接入主链、后端主链技术集成 |
| 关联正式交付章节 | docs/deliverables/system-development-and-operation-guide.md；docs/deliverables/安全智能体系统设计说明书V2.md |
| 对应PR或Commit | 当前 main 分支：5c05d61；本文件为工作区新增文档 |
| 最后更新时间 | 2026-08-26 |
| 最后复验时间 | 2026-08-26 |

## 1. 目标与非目标

### 1.1 目标

- 将告警接入、告警关联、风险研判、深度调查、处置决策、审批、处置执行、处置验证串成统一后端主流程。
- 通过 `EventContext` 统一承载一次安全事件处理的上下文、状态、时间线、证据、处置结果和错误信息。
- 通过 `StateMachine` 约束业务状态流转，避免业务模块绕过编排层直接修改状态。
- 通过 `ToolRequest` / `ToolResult` 统一工具调用契约，使 fixed/jsonl 平台适配器和 MVP Mock 工具可以被主链调度。
- 对外提供 HTTP 接口，支持启动主流程、查询事件、查询时间线、提交审批和查看基础指标。

### 1.2 非目标

- 本阶段不直接实现真实深信服 MCP / XDR OpenAPI 全量调用，当前仍以 fixed_sample、jsonl_sample 和 Mock 工具为主。
- 本阶段不实现真实高风险处置动作，执行阶段当前使用 `stateful_response_mock` 类型能力。
- 本阶段不实现长流程异步队列、断点续跑和分布式任务调度。
- 本阶段不保证 deep agent 在未配置 LLM 和外部工具服务时真实闭环运行。

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
| `StartRunRequest.xdr_event_id` | `str | None` | 否 | API 或脚本 | 真实 XDR 事件 ID；当前已具备适配器边界，实机路径、鉴权和分页仍待联调确认 |
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
- 失败、超时与人工接管：接入失败会生成 `FAILED` 事件；调查证据不足、审批拒绝或验证异常可进入 `HUMAN_REQUIRED`。
- 真实执行与Mock边界：当前处置执行和验证仍以 Mock / 样例工具为主，不代表真实平台已经完成高风险动作。

## 7. 关键设计决策

| 决策 | 原因 | 未采用方案及原因 |
|---|---|---|
| 使用 `Orchestrator` 作为唯一主链编排入口 | 保证状态推进、仓储写入和模块调用顺序集中可控 | 未让各模块自行推进状态，避免状态不一致 |
| 使用 `EventContext` 作为主链上下文 | 便于 API、仓储、测试和前端统一读取处理结果 | 未拆成多个临时对象，避免主链结果分散 |
| 使用 `StateMachine` 限制状态迁移 | 防止非法回退、跳跃和终态继续推进 | 未直接在服务中修改字符串状态，避免缺少约束 |
| 使用 `ToolRequest` / `ToolResult` 统一工具契约 | 便于 fixed/jsonl、Mock 工具和后续真实平台工具共用调度接口 | 未让不同工具返回任意 dict，避免下游解析混乱 |
| 保留 `memory` 和 `mysql` 两类仓储 | 本地开发可快速运行，后续可切 MySQL 持久化 | 未强制所有环境依赖 MySQL，降低本地调试门槛 |

## 8. 非功能、可观测与审计要求

| 维度 | 当前要求或设计 | 验证方式 |
|---|---|---|
| 性能与时延 | 当前主链为同步调用，适用于 MVP 样例和接口联调；暂未定义生产时延 SLA | `pytest`、`run_flow`、HTTP 接口测试 |
| 稳定性与可重复性 | fixed_sample 和 jsonl_sample 应可重复产生稳定状态线；审批幂等键避免重复执行 | `tests/test_state_flow.py`、`tests/test_jsonl_platform.py` |
| 可观测性 | `EventContext.timeline` 记录状态变化；`errors` 记录失败阶段；`trace_id` 串联工具调用；`requested_source/effective_source/fallback_source` 区分请求来源、实际来源和降级来源 | 查询 `/events/{event_id}`、`/events/{event_id}/timeline` |
| 审计与追踪 | `trace_id`、`run_id`、`event_id`、`idempotency_key`、`ToolRequest.call_id`、`ToolResult.raw_result_ref` 支持基本追踪 | API 响应、仓储记录、测试断言 |

## 9. 当前限制与后续事项

| 限制或未实现项 | 对主链影响 | 后续条件/负责人 |
|---|---|---|
| 真实深信服 MCP / XDR OpenAPI 未完成接入 | 不阻塞 MVP 主链；阻塞真实平台闭环 | 补齐调用地址、鉴权、字段映射和集成测试 |
| 真实高风险处置动作未接入 | 不阻塞主链演示；阻塞生产处置能力 | 接入真实处置 API，并明确审批、回滚和审计 |
| 主链当前以同步方式执行 | 不阻塞本地和 CI；高并发或长任务场景待优化 | 引入异步任务、队列、状态持久化和重试策略 |
| MySQL 仓储需要真实数据库环境复验 | 不阻塞 memory 模式；影响持久化上线 | 准备 MySQL 环境并补充迁移、清理和回归测试 |
| `xdr` 请求来源为模型保留值 | 不阻塞 fixed/jsonl；直接请求真实 xdr 当前不可用 | 平台适配器补齐真实 XDR 后端 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-26 | 当前工作区新增 | 新增主链模块设计文档，按现有 Orchestrator 和状态机补充内容 | 否 |
