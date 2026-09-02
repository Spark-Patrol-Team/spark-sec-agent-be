# 主链开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 负责人 | 李雨妍 |
| 文档状态 | 已保存至docs文件夹下 |
| 实现状态 | 主链已实现；真实 XDR 告警列表拉取已完成一次实机验证 |
| 能力性质 | 自研代码；fixed_sample / jsonl_sample / xdr_openapi / Mock / fallback 混合能力 |
| 关联任务/需求 | 后端主链技术集成、统一工具调度、状态流转、HTTP 接口联调 |
| 关联正式交付章节 | docs/deliverables/system-development-and-operation-guide.md；第9章模块说明与接入位置 |
| 对应PR或Commit | 当前工作区；建议提交名 `fix: align XDR OpenAPI auth and alert ingestion` |
| 适用代码版本 | 当前工作区，包含真实 XDR 告警接入与主链文档补充 |
| 最后更新时间 | 2026-08-30 |

## 1. 当前实现摘要

### 1.1 已实现

- `Orchestrator.start()` 已串联告警接入、告警关联、风险研判、深度调查、处置决策和审批等待。
- `Orchestrator.approve()` 已支持审批通过后执行处置与验证，审批拒绝进入人工处理。
- `StateMachine` 已约束主链允许的状态迁移，非法迁移会抛出 `InvalidStatusTransition`。
- `EventContext` 已作为统一上下文返回给 API、脚本和仓储。
- HTTP 接口已支持 `POST /runs`、`GET /events`、`GET /events/{event_id}`、`GET /events/{event_id}/timeline`、`POST /events/{event_id}/approval`。
- `build_container()` 已根据配置组装平台适配器、仓储和主链编排器。
- fixed_sample 和 jsonl_sample 均可接入主链，并经过现有测试覆盖。
- `xdr_openapi` 可通过 `POST /api/xdr/v1/alerts/list` 从真实 XDR 拉取告警列表，并经 `POST /runs` 进入主链。
- XDR 官方 AK/SK/联动码签名已在后端实现，签名结果已与官方 `aksk_py3.py` 固定样例对齐。
- `xdr_event_id` 当前按返回结果里的唯一标识本地匹配，不依赖上游接口支持 `uuId` 过滤。
- 统一工具调度已接入调查、处置和验证链路，工具结果统一落在 `ToolResult` 契约中。

### 1.2 未实现或未复验

- XDR OpenAPI 目前只完成告警列表接口验收，不代表全量 XDR 接口能力完成。
- 真实深信服 MCP 工具尚未完成主链实机闭环复验。
- XDR 日志查询接口路径、权限和返回结构尚未拿到完整契约；当前作为调查补充工具，不阻断已命中告警进入审批。
- 真实高风险处置动作尚未接入，当前执行阶段仍为 Mock 能力。
- 主链尚未实现异步任务队列、超时调度、后台重试和断点续跑。
- MySQL 持久化已有代码路径，但需要真实数据库环境复验。
- deep agent 真实 LLM 闭环依赖 `LLM_API_KEY` 和外部工具配置，未配置时会走 fallback 或跳过真实集成测试。

## 2. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/api/routes/events.py` | `start_run()`、`submit_approval()` | 主链 HTTP 启动、查询和审批入口 |
| `src/sec_agent/api/app.py` | `create_app()` | 创建 FastAPI 应用，挂载路由、中间件和运行容器 |
| `src/sec_agent/api/deps.py` | `get_orchestrator()` | 从应用状态中获取主链编排器 |
| `src/sec_agent/bootstrap/container.py` | `build_container()`、`AppContainer` | 根据配置装配平台、仓储和 `Orchestrator` |
| `src/sec_agent/services/orchestrator.py` | `Orchestrator` | 主链编排核心，负责调用模块和推进状态 |
| `src/sec_agent/domain/state_machine.py` | `StateMachine`、`ALLOWED_TRANSITIONS` | 状态流转约束 |
| `src/sec_agent/domain/models.py` | `EventContext`、`BusinessStatus`、`StartRunRequest`、`ApprovalDecision` | 主链核心数据模型 |
| `src/sec_agent/services/ingest.py` | `AlertIngestService` | 告警接入服务 |
| `src/sec_agent/services/correlation.py` | `AlertCorrelationService` | 告警关联服务 |
| `src/sec_agent/services/triage.py` | `RiskTriageService` | 风险研判服务 |
| `src/sec_agent/services/investigation.py` | `DeepInvestigationAgent` | 深度调查统一入口 |
| `src/sec_agent/services/deep_agent_bridge.py` | `DeepAgentBridge` | deep agent 桥接与 fallback |
| `src/sec_agent/services/response.py` | `ResponseDecisionService`、`ResponseExecutionService`、`ResponseVerificationService` | 处置决策、执行和验证 |
| `src/sec_agent/platforms/base.py` | `PlatformAdapter` | 平台接入和工具调用抽象 |
| `src/sec_agent/platforms/fixed_sample.py` | `FixedSampleAdapter` | 固定样例平台适配器 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | JSONL 样例平台适配器 |
| `src/sec_agent/platforms/xdr_openapi.py` | `XdrOpenApiAdapter`、`XdrOfficialSigner` | 真实 XDR 告警输入、官方签名和平台工具边界 |
| `src/sec_agent/repositories/memory.py` | `InMemoryEventRepository` | 本地内存仓储 |
| `src/sec_agent/repositories/mysql.py` | `MySQLEventRepository` | MySQL 仓储 |
| `src/sec_agent/scripts/run_flow.py` | `main()` | 本地主流程演示脚本 |

## 3. 依赖与配置

| 名称 | 必需/可选 | 获取方式 | 未配置时行为 |
|---|---|---|---|
| `PYTHONPATH=src` | 必需 | 启动命令中指定或安装 editable 包 | 找不到 `sec_agent` 包 |
| `APP_ENV` | 可选 | 环境变量或 `.env` | 默认 `local` |
| `STORAGE_BACKEND` | 可选 | 环境变量或 `.env` | 默认 `memory` |
| `PLATFORM_BACKEND` | 可选 | 环境变量或 `.env` | 默认 `fixed_sample` |
| `XDR_BASE_URL` | xdr_openapi 必需 | 环境变量或本地 `.env` | 缺失时启动校验失败 |
| `XDR_AUTH_TYPE` | xdr_openapi 必需 | `token` / `aksk` / `auth_code` | 默认 `token`；真实联调用 `auth_code` |
| `XDR_AUTH_CODE` | `auth_code` 模式必需 | 官方联动码，本地 `.env` | 缺失时启动校验失败 |
| `XDR_ACCESS_KEY` / `XDR_SECRET_KEY` | `aksk` 模式必需 | 官方 AK/SK | 缺失时启动校验失败 |
| `XDR_ALERTS_PATH` | xdr_openapi 可选 | 环境变量或 `.env` | 默认 `/api/xdr/v1/alerts/list` |
| `XDR_ALERT_PAGE_SIZE` | xdr_openapi 可选 | 环境变量或 `.env` | 默认 `50` |
| `XDR_ALERT_MAX_PAGES` | xdr_openapi 可选 | 环境变量或 `.env` | 默认 `20` |
| `XDR_ALERT_START_TIMESTAMP` | xdr_openapi 可选 | 环境变量或 `.env` | 未配置时不传 `startTimestamp` |
| `XDR_VERIFY_SSL` | xdr_openapi 可选 | 环境变量或 `.env` | 默认 `false`，适配内网自签证书联调 |
| `JSONL_SAMPLE_DIR` | jsonl 模式必需 | 环境变量或默认路径 | 默认 `tests/fixtures/fixed_alerts` |
| `JSONL_INPUT_MODE` | 可选 | 环境变量或 `.env` | 默认 `normalized` |
| `INVESTIGATION_BACKEND` | 可选 | 环境变量或 `.env` | 默认 `auto` |
| `MYSQL_DSN` | MySQL 模式必需 | 环境变量或拆分 MySQL 配置拼接 | memory 模式不需要；MySQL 模式连接失败会影响运行 |
| `LLM_API_KEY` | deep agent 真实 LLM 可选/必需 | 环境变量 | 未配置时真实 LLM 集成不可运行，测试中对应用例跳过或 fallback |
| `CORS_ALLOWED_ORIGINS` | 前端联调可选 | 环境变量 | 默认允许本地常见前端端口 |

- 支持的运行环境：当前本地验证使用 Python 3.11；项目代码已兼容 Python 3.9 的枚举实现调整。
- 敏感配置只通过环境变量或受控配置注入，不在文档、代码和样例中填写真实值。

## 4. 启动与调试

本地主流程脚本：

```text
PYTHONPATH=src PLATFORM_BACKEND=fixed_sample python -m sec_agent.scripts.run_flow
```

- 成功判据：输出启动事件、审批后状态和状态时间线；fixed_sample 高风险样例审批后应进入 `COMPLETED`。
- 常见失败及排查：如提示找不到 `sec_agent`，检查是否设置 `PYTHONPATH=src` 或是否已执行 editable 安装。

HTTP 服务：

```text
PYTHONPATH=src APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=fixed_sample python -m uvicorn sec_agent.main:app --host 127.0.0.1 --port 8000
```

- 成功判据：`GET /health` 返回 `status=ok`；`POST /runs` 返回 `EventContext`。
- 常见失败及排查：如 CORS 不生效，检查 `CORS_ALLOWED_ORIGINS` 是否包含前端实际 origin。

真实 XDR 告警输入本地启动：

```text
PLATFORM_BACKEND=xdr_openapi INVESTIGATION_BACKEND=tool_mock uv run uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
```

- 前置条件：本地 `.env` 已配置 `XDR_BASE_URL`、`XDR_AUTH_TYPE=auth_code`、`XDR_AUTH_CODE`、`XDR_ALERTS_PATH=/api/xdr/v1/alerts/list`、`XDR_ALERT_START_TIMESTAMP=1787155200`。
- 成功判据：`POST /runs` 携带已知 `xdr_event_id` 后，返回 `requested_source=xdr`、`effective_source=xdr_openapi`、`fallback_source=null`，并进入 `APPROVAL_REQUIRED`。

## 5. 调用与接入方法

### 5.1 调用入口

- HTTP 启动主链：`POST /runs`
- HTTP 查询事件列表：`GET /events`
- HTTP 查询事件详情：`GET /events/{event_id}`
- HTTP 查询状态时间线：`GET /events/{event_id}/timeline`
- HTTP 提交审批：`POST /events/{event_id}/approval`
- 代码入口：`build_container().orchestrator.start(StartRunRequest(...))`
- 本地脚本入口：`python -m sec_agent.scripts.run_flow`

### 5.2 最小示例

启动 fixed_sample 主链：

```text
curl -s -X POST 'http://127.0.0.1:8000/runs' \
  -H 'Content-Type: application/json' \
  -d '{"source":"fixed_sample","sample_id":"webshell-001"}'
```

脱敏响应示例：

```text
{
  "trace_id": "trace-<uuid>",
  "run_id": "run-<uuid>",
  "event_id": "evt-<uuid>",
  "status": "APPROVAL_REQUIRED",
  "source": "fixed_sample",
  "alert_refs": ["xdr-alert-001", "xdr-alert-002"]
}
```

审批通过：

```text
curl -s -X POST 'http://127.0.0.1:8000/events/<event_id>/approval' \
  -H 'Content-Type: application/json' \
  -d '{"approved":true,"approver":"local-test","reason":"本地联调审批","idempotency_key":"<event_id>:approval:1"}'
```

脱敏响应示例：

```text
{
  "event_id": "evt-<uuid>",
  "status": "COMPLETED",
  "response": {
    "execution": {"status": "success"},
    "verification": {"final_status": "COMPLETED"}
  }
}
```

启动真实 XDR 告警主链：

```text
curl -s -X POST 'http://127.0.0.1:8000/runs' \
  -H 'Content-Type: application/json' \
  -d '{"source":"xdr","xdr_event_id":"alert-9fd0c034-ba09-4311-8360-cf1787206450"}'
```

脱敏验收输出摘要：

```text
status=APPROVAL_REQUIRED
requested_source=xdr
effective_source=xdr_openapi
fallback_source=null
alert_refs=["alert-9fd0c034-ba09-4311-8360-cf1787206450"]
errors=[]
timeline=RECEIVED,CORRELATING,TRIAGED,INVESTIGATING,DECISION_READY,APPROVAL_REQUIRED
```

### 5.3 上下游接入注意事项

- 新增业务阶段必须同步修改 `BusinessStatus`、`ALLOWED_TRANSITIONS`、`Orchestrator`、API 响应模型和测试。
- 业务模块只返回结果，不直接修改 `EventContext.status`。
- 工具调用必须优先走 `ToolRequest` / `ToolResult`，不要在主链中直接传递任意结构。
- 需要产生外部副作用的动作必须明确 `risk_level`、审批要求、幂等键和回滚边界。
- `ApprovalDecision.idempotency_key` 必须由调用方保证稳定，避免重复审批触发重复执行。
- 对真实 XDR `xdr_event_id` 的筛选只在本地完成，除非上游明确提供可用过滤参数，否则不要把 `uuId` 直接加入请求体。

## 6. 异常处理与安全控制

- 输入错误：Pydantic 和 FastAPI 返回参数校验错误；未知事件审批返回 404；非审批状态提交审批返回 409。
- 依赖或工具失败：接入阶段失败会生成 `FAILED` 事件；编排阶段异常会记录 `ErrorRecord(stage="orchestrator")` 并进入 `FAILED`。
- 重复调用与幂等：审批通过使用仓储的 `claim_idempotency_key()` 防止重复执行；同一幂等键重复提交返回当前上下文。
- 超时、重试与回滚：`ToolRequest` 已包含超时、尝试次数和幂等字段；主链尚未实现统一后台重试和自动回滚调度。
- 权限、审批与敏感数据：高风险计划默认进入审批等待；真实密钥、内网地址和 Token 不写入仓库。

## 7. 真实平台、Mock与fallback边界

| 能力 | 当前实际实现 | 触发条件 | 不得误写为 |
|---|---|---|---|
| 告警输入 | fixed_sample / jsonl_sample / xdr_openapi | `PLATFORM_BACKEND=fixed_sample`、`jsonl_sample` 或 `xdr_openapi` | 真实 XDR 已完整闭环 |
| XDR 告警列表 | 真实 OpenAPI 单接口已验收 | `PLATFORM_BACKEND=xdr_openapi` 且配置官方鉴权 | XDR 全量接口均已完成 |
| JSONL 接入 | 本地实现 | `JsonlSampleAdapter` 读取样例目录 | 真实平台实时拉取 |
| 深度调查 | 本地工具链 / deep agent 桥接 / fallback | `INVESTIGATION_BACKEND` 控制 | 未配置 LLM 时的真实 Agent 闭环 |
| XDR 日志查询 | fixed_sample/jsonl_sample 下为内置样例；xdr_openapi 下可走 OpenAPI handler 或注入真实 handler；失败不阻断已命中告警审批 | `xdr_log_query` | 已完成日志接口实机验收 |
| 处置执行 | Mock / stateful mock | 高风险审批通过后 | 真实封禁、隔离或资产处置 |
| 处置验证 | Mock / stateful mock | 执行后验证阶段 | 真实平台验证闭环 |
| 事件存储 | memory / MySQL 代码路径 | `STORAGE_BACKEND` 控制 | 已完成所有生产数据库迁移 |

## 8. 已知限制与待办

| 优先级 | 事项 | 是否影响主链 | 负责人/完成条件 |
|---|---|---|---|
| P0 | 真实平台 MCP 工具闭环 | 是，影响生产调查闭环 | 补齐 MCP 地址、鉴权、工具 schema 和集成测试 |
| P0 | 真实高风险处置动作和回滚策略 | 是，影响生产处置 | 接入真实处置 API，补审批、回滚、审计测试 |
| P1 | XDR 日志查询接口契约确认 | 否，不影响告警输入 | 索要日志查询真实路径、请求参数、返回结构和权限说明 |
| P1 | XDR 告警更多样本覆盖 | 否，不影响当前已知告警 | 补齐不同严重级别、不同攻击类型和空字段样本 |
| P1 | MySQL 模式真实环境复验 | 待确认 | 准备数据库和迁移策略，完成接口回归 |
| P1 | 主链异步化、超时和重试策略 | 否，不影响 MVP | 引入任务队列或后台任务模型 |
| P2 | `docs/modules/orchestration` 与 `docs/modules/main-chain` 边界整理 | 否 | 后续统一命名或建立索引 |

## 9. 运行观测、版本兼容与迁移

- 日志与关键指标位置：当前以 API 返回的 `EventContext.timeline`、`EventContext.errors`、`ToolResult` 字段和 `/metrics` 基础指标为主。
- 健康检查或运行状态判断：`GET /health` 查看运行配置；`GET /events` 查看事件列表；`GET /events/{event_id}/timeline` 查看主链状态线。
- 兼容的接口/Schema/平台版本：OpenAPI 产物位于 `docs/swagger/openapi.json`；业务上下文 schema 版本为 `2026-08-21.mvp.v1`。
- 升级、迁移或回退注意事项：新增状态、接口字段或工具契约时必须同步更新 OpenAPI、测试和模块文档；生产迁移 MySQL 前需要验证表结构兼容。

## 10. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-26 | 当前工作区新增 | 新增主链开发说明，记录当前代码入口、配置、调用方式和边界 | `docs/modules/main-chain/test.md` |
| 2026-08-30 | 当前工作区更新 | 补充真实 XDR 告警输入配置、调用示例、实机验收结果和能力边界 | `tests/test_xdr_openapi_platform.py` |
