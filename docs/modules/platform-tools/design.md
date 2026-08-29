# 平台工具模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 平台工具模块（Platform Tools） |
| 负责人 | 杨嘉琪 |
| 文档状态 | 已复验 |
| 实现状态 | 固定样例、JSONL 样例和 Mock 工具已实现并复验；真实 XDR 只读查询待平台条件就绪后接入 |
| 能力性质 | 自研代码、固定样例、Mock、fallback；真实平台能力为候选项，当前未接通 |
| 关联任务/需求 | `T0826-07` 平台工具调度器复测；`T0827-05` 工具模块收口与真实平台接入准备 |
| 关联正式交付章节 | 系统设计说明书中的平台工具、调查编排与安全边界章节；具体章号待总文档负责人统一 |
| 对应 PR 或 Commit | 复测基线 `main@95defad5e6d8a44fdb601d844d876f25544f479d`；本文档 PR 待创建 |
| 最后更新时间 | 2026-08-28 |
| 最后复验时间 | 2026-08-28 |

## 1. 目标与非目标

### 1.1 目标

- 为业务 service 和 Agent 提供唯一、统一、可审计的工具调用入口。
- 使用 `ToolRequest` 和 `ToolResult` 统一工具输入、输出、错误和副作用描述。
- 在同一调度器中注册证据查询、XDR 日志查询、有状态 Mock、Mock 响应和响应验证能力。
- 对未知工具返回结构化失败结果，不向上层抛出未处理的查找异常。
- 保持固定样例、JSONL 样例、Mock 和未来真实平台之间清晰的数据来源边界。
- 为真实 XDR 只读查询预留最小适配位置，取得权限和接口后不需要重建调度链路。

### 1.2 非目标

- 当前不声明真实 XDR OpenAPI 已接通。
- 当前内置 `xdr_log_query` 不代表真实平台数据。
- 本模块不负责研判规则、风险阈值和 Agent 决策逻辑。
- 本阶段不实现真实隔离、封禁、删除等有副作用处置动作。
- 本模块不保存真实凭据，不在源码、文档、日志或样例中记录 Token、Secret 和内网地址。
- 不新建第二套 `ToolDispatcher`、XDR 专用调度器或平行工具契约。

## 2. 职责与边界

- 本模块负责：工具注册与分发、工具输入输出契约、结构化错误、审计字段、副作用标记、固定样例与 Mock 能力装配，以及真实平台适配入口。
- 本模块不负责：Agent 研判决策、前端展示逻辑、真实 XDR 字段标准制定、生产凭据发放和真实处置审批。
- 需要人工参与的环节：真实平台权限申请、接口与字段确认、凭据托管、脱敏规则确认，以及所有未来高风险真实动作的审批。

## 3. 输入与输出

### 3.1 输入

统一输入对象为 `ToolRequest`。

| 字段/对象 | 类型 | 必填 | 来源 | 含义与约束 |
|---|---|---|---|---|
| `call_id` | `str` | 否 | 模型自动生成 | 单次工具调用标识 |
| `trace_id` | `str` | 是 | 上游编排链 | 跨模块追踪标识 |
| `event_id` | `str` | 是 | 安全事件 | 关联事件标识 |
| `stage` | `BusinessStatus` | 是 | 状态机/业务 service | 调用发生时的业务阶段 |
| `tool_name` | `str` | 是 | Agent 或业务 service | 必须匹配已注册工具名 |
| `action_name` | `str` | 是 | Agent 或业务 service | 工具内具体动作 |
| `params` | `dict` | 是 | 调用方 | 参数需在 handler 内校验；敏感字段需脱敏 |
| `reason` | `str` | 是 | 调用方 | 调用原因和审计说明 |
| `idempotency_key` | `str` | 是 | 调用方 | 幂等与动作追踪标识 |
| `risk_level` | `ToolRiskLevel` | 是 | 调用方 | 工具风险等级 |
| `approval_status` | `ApprovalStatus` | 否 | 审批流程 | 高风险动作的审批状态；只读查询通常无需审批 |
| `timeout_seconds` | `int` | 否 | 调用配置 | 调用超时上限 |
| `attempt` / `max_attempts` | `int` | 否 | 调度或重试逻辑 | 当前尝试次数和最大次数 |
| `sensitive_param_keys` | `list[str]` | 否 | 调用方 | 审计输出时需要遮蔽的参数键 |

### 3.2 输出

统一输出对象为 `ToolResult`。

| 字段/对象 | 类型 | 去向 | 含义与约束 |
|---|---|---|---|
| `call_id` / `trace_id` / `event_id` | `str` | 上游编排、日志和审计 | 与请求保持关联 |
| `tool_name` / `action_name` | `str` | 上游调用方 | 标识实际工具和动作 |
| `idempotency_key` | `str` | 幂等与验证流程 | 与请求保持一致 |
| `status` | `ToolCallStatus` | Agent、业务 service、前端 | `SUCCESS`、`FAILED` 或 `PARTIAL_SUCCESS` |
| `summary` | `str` | 上游和审计 | 可展示的脱敏摘要 |
| `raw_result_ref` | `str \| None` | 证据/审计 | 原始结果引用，不直接承载敏感原文 |
| `evidence_refs` / `output_refs` | `list[str]` | 调查链和证据链 | 证据及输出引用 |
| `output_preview` | `dict` | Agent、业务 service、前端 | 脱敏后的结构化预览 |
| `retryable` | `bool` | 上层调度逻辑 | 是否允许重试或替换其他工具 |
| `error_type` / `error_message` | 枚举/字符串 | 上层错误处理 | 结构化错误类型及脱敏说明 |
| `external_side_effect` | `bool` | 审批和安全控制 | 是否产生外部系统副作用 |
| `side_effect_type` | `ToolSideEffectType` | 审批和审计 | `NONE`、`READ_ONLY` 或 `STATE_CHANGE` |
| 时间及尝试字段 | 时间/整数 | 可观测与审计 | 记录开始、结束、耗时和尝试次数 |

## 4. 核心流程与状态变化

1. Agent 或业务 service 根据当前事件和业务阶段构造 `ToolRequest`。
2. 平台适配器将请求交给当前唯一 `ToolDispatcher`。
3. `ToolDispatcher` 根据 `tool_name` 在 handler 映射中查找处理函数。
4. 已注册工具执行参数校验、样例读取、证据查询或 Mock 状态操作。
5. handler 返回完整 `ToolResult`，包含状态、审计字段、输出预览、错误和副作用描述。
6. 未注册工具不执行外部调用，直接返回 `FAILED / UNSUPPORTED_TOOL / retryable=true`。
7. 调查或响应 service 根据结构化结果继续编排、重新选择工具、进入审批或人工处理。

平台工具模块本身不直接推进业务状态机。业务状态变化由调查、响应和编排 service 根据 `ToolResult` 决定。

## 5. 上下游关系与契约

| 方向 | 模块/接口 | 契约或文档位置 | 当前状态 |
|---|---|---|---|
| 上游 | 调查 service | `src/sec_agent/services/investigation.py`、`ToolRequest` | 已对齐 |
| 上游 | 响应 service | `src/sec_agent/services/response.py`、`ToolRequest` | 已对齐 |
| 上游 | 平台适配器 | `src/sec_agent/platforms/fixed_sample.py`、`jsonl_sample.py` | 已对齐 |
| 核心 | 工具调度器 | `src/sec_agent/tools/base.py`、`tool_dispatcher.py` | 已复验 |
| 下游 | 固定/JSONL 样例 | `src/sec_agent/platforms/`、`tests/fixtures/` | 已实现并复验 |
| 下游 | 真实 XDR 只读接口 | `docs/modules/platform-tools/xdr-readonly-readiness.md` | 待平台条件就绪 |
| 下游 | 审计与证据链 | `ToolResult` 的引用和审计字段 | 已对齐 |

## 6. 安全边界

- 权限与审批：只读查询必须使用最小只读权限；未来真实有副作用动作必须单独设计审批，不复用 Mock 作为真实执行证明。
- 输入校验：handler 必须校验必填参数、类型、时间范围、分页和平台限制；非法参数不得发往外部平台。
- 敏感信息处理：凭据不进入源码、Markdown、样例、日志、异常堆栈和前端响应；`sensitive_param_keys` 用于审计脱敏。
- 失败、超时与人工接管：平台错误统一转换为结构化 `ToolResult`；不可恢复错误由上层决定是否人工处理。
- 真实执行与 Mock 边界：真实平台、固定样例、JSONL 样例和 Mock 必须具有不同的数据来源标识；不得静默用样例结果冒充真实数据。
- 只读边界：真实 XDR 查询应返回 `external_side_effect=false`、`side_effect_type=READ_ONLY`。

## 7. 关键设计决策

| 决策 | 原因 | 未采用方案及原因 |
|---|---|---|
| 保留唯一 `ToolDispatcher` | 避免多套注册表和错误契约分叉 | 不新建 XDR 专用调度器，避免业务链选择入口 |
| 使用 handler 映射分发 | 工具扩展简单，测试可注入 | 不在 service 中写大量工具名条件分支 |
| 通过 `extra_handlers` 扩展或覆盖 | 真实平台可覆盖默认 `xdr_log_query`，不破坏现有样例 | 不直接把 HTTP 调用写进固定/JSONL 样例适配器 |
| 统一使用 `ToolRequest` / `ToolResult` | 保持审计、错误和副作用字段一致 | 不为真实 XDR 新建平行响应模型 |
| 未知工具返回结构化错误 | 上层可以识别并选择其他工具 | 不抛出未捕获 `KeyError`，不返回模糊空值 |
| 固定样例 fallback 必须显式启用并标源 | 防止演示数据被误认为真实数据 | 不允许平台失败后静默伪装成功 |

## 8. 非功能、可观测与审计要求

| 维度 | 当前要求或设计 | 验证方式 |
|---|---|---|
| 性能与时延 | 记录 `duration_ms`；真实平台超时应受 `timeout_seconds` 和配置限制 | 单元/集成测试及运行日志 |
| 稳定性与可重复性 | 固定样例与 JSONL 样例可重复；有状态 Mock 在同一 ledger 生命周期内保持状态 | `tests/test_mvp_tool.py`、集成测试 |
| 可观测性 | 返回状态、摘要、平台状态、错误类型、重试属性及输出预览 | 检查 `ToolResult` |
| 审计与追踪 | 保留 `call_id`、`trace_id`、`event_id`、`idempotency_key`、尝试次数和时间字段 | 工具契约测试与结果记录 |
| 数据来源 | 固定、JSONL、内置 XDR 和未来真实 XDR 必须可区分 | 检查 `source`、引用前缀和输出来源标识 |

## 9. 当前限制与后续事项

| 限制或未实现项 | 对主链影响 | 后续条件/负责人 |
|---|---|---|
| `handle_xdr_query()` 当前固定返回一条内置 SQL 注入日志 | 不阻塞固定样例主链；阻塞真实 XDR 验证 | 获得 XDR 接口、权限、鉴权和脱敏样例后实现真实 adapter |
| 真实 XDR 配置名称和接口字段尚未确认 | 不阻塞当前样例链 | 平台负责人确认，杨嘉琪完成适配说明 |
| 真实平台错误码映射尚未实测 | 不阻塞当前样例链 | 取得成功、空结果和错误响应样例后补测 |
| Stateful Mock 状态仅保存在内存中 | 不阻塞演示；不能作为真实动作记录 | 真实动作由响应模块另行设计持久化和审批 |
| Windows 缺少 `tzdata` 时无法加载 `Asia/Shanghai` | 不影响 Linux 主链；影响部分 Windows 本地测试 | Windows `.venv` 安装 `tzdata` |
| XDR OpenAPI、MCP、FastGPT/OpenClaw 真实接入未完成 | 当前不阻塞固定样例主链 | 按平台优先级逐项接入和复验 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-26 | `5defad5e6d8a44fdb601d844d876f25544f479d` | `T0826-07`：平台工具调度器目标测试复验及 Windows `tzdata` 问题记录 | 是 |
| 2026-08-28 | `95defad5e6d8a44fdb601d844d876f25544f479d` | `T0827-05`：统一调度结构复核、五类工具复测和真实 XDR 就绪设计补充 | 是 |

