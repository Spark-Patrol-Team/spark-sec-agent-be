# XDR 真实只读查询接入就绪说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 任务 ID | `T0827-05` |
| 负责人 | 杨嘉琪 |
| 模块 | 平台工具调度器 / XDR 只读查询适配 |
| 基线 | `main@95defad5e6d8a44fdb601d844d876f25544f479d` |
| 编写日期 | 2026-08-28 |
| 当前状态 | 接入准备中，等待真实平台权限、接口文档和脱敏样例 |
| 能力性质 | 真实平台只读能力候选；当前内置 XDR 数据仍属于固定样例 |

## 1. 目标与边界

### 1.1 目标

- 梳理真实 XDR 只读查询所需的权限、接口、鉴权、字段和环境条件。
- 明确真实查询能力接入现有工具调度链路的最小位置。
- 在不改变现有 `ToolRequest`、`ToolResult` 和统一调度入口的前提下，为真实平台适配做好准备。
- 明确成功、未知工具、鉴权失败、超时、平台不可达和空结果的结构化返回。
- 明确真实平台和固定样例 fallback 的边界，避免将样例数据误标为真实平台数据。

### 1.2 非目标

- 本文不声明真实 XDR 已经接通。
- 本文不记录真实 Token、Secret、内网地址、证书或未脱敏平台响应。
- 本阶段不实现告警处置、隔离、封禁等有副作用动作。
- 本阶段不另建第二套工具调度器或独立调度链路。
- 真实 XDR 字段到标准告警契约的详细映射由字段映射任务负责，本文只记录适配所需接口边界。

## 2. 当前复测基线

在基线 `main@95defad5e6d8a44fdb601d844d876f25544f479d` 上，使用 Windows 本地 `.venv`、Python `3.13.9` 执行：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_tool_dispatcher_integration.py tests/test_mvp_tool.py
```

实际结果：

```text
6 passed in 0.13s
```

结果范围：

- `tests/test_tool_dispatcher_integration.py`：3 项通过；
- `tests/test_mvp_tool.py`：3 项通过；
- 合计：6 项通过，0 项跳过，0 项失败；
- 本结果仅代表上述两份目标测试，不表述为最新主干完整 pytest 全部通过。

## 3. 当前已验证的工具能力

| 工具名 | 当前性质 | 注册状态 | 调度状态 | 说明 |
|---|---|---|---|---|
| `evidence_lookup` | 固定样例/本地实现 | 已验证 | 已验证 | 查询关联证据 |
| `xdr_log_query` | 当前为内置固定样例 | 已验证 | 已验证 | 真实 XDR 只读查询的目标接入点 |
| `stateful_mock` | 有状态 Mock | 已验证 | 已验证 | 验证同一会话内的内存状态合并 |
| `stateful_response_mock` | 有状态响应 Mock | 已验证 | 已验证 | 模拟处置动作记录，不代表真实平台动作 |
| `response_verify` | 固定样例/Mock 验证 | 已验证 | 已验证 | 验证 Mock 动作状态 |

## 4. 真实平台能力候选与就绪矩阵

| 候选能力 | 优先级 | 所需权限 | 接口与方法 | 鉴权 | 关键输入 | 关键输出 | 当前阻塞 | 近期可完成性 |
|---|---|---|---|---|---|---|---|---|
| 按时间范围查询 XDR 事件 | P0 | 事件列表只读权限 | 待平台方确认 | 待平台方确认 | 开始时间、结束时间、分页、过滤条件 | 事件 ID、发生时间、规则名、风险等级、源/目的地址、资产引用 | 权限、接口文档、凭据、脱敏样例 | 最有可能完成 |
| 按事件 ID 查询详情 | P0 | 事件详情只读权限 | 待平台方确认 | 待平台方确认 | 事件 ID | 事件详情、攻击阶段、资产信息、证据引用、原始记录引用 | 字段字典、详情接口、样例响应 | 较可能完成 |
| 查询事件关联日志或证据 | P1 | 日志/证据只读权限 | 待平台方确认 | 待平台方确认 | 事件 ID、时间范围或查询表达式 | 脱敏日志摘要、证据引用、日志时间线 | 数据权限、脱敏规则、返回体规模限制 | 待确认 |
| 查询资产基础信息 | P1 | 资产只读权限 | 待平台方确认 | 待平台方确认 | 资产 ID、IP 或主机名 | 资产 ID、类型、名称、重要性和状态 | 资产接口权限、字段定义 | 待确认 |

当前优先候选是“按时间范围查询 XDR 事件”和“按事件 ID 查询详情”。这两项均为只读操作，不产生外部处置副作用；但在平台方确认权限和接口前，只能标记为候选能力，不能标记为已接入。

## 5. 待平台方确认的信息

### 5.1 网络与接口

- XDR API Base URL 和 API 版本；
- 开发、测试和生产环境是否分别提供地址；
- 是否要求 VPN、IP 白名单、专线、代理或双向 TLS；
- 事件列表、事件详情、关联日志和资产查询的接口路径及 HTTP 方法；
- 接口的分页方式、单页上限、最大时间范围和速率限制；
- 请求和响应的字符编码、时间格式及时区约定。

### 5.2 权限与鉴权

- 鉴权方式：API Key、Bearer Token、OAuth2、签名或客户端证书；
- 获取和轮换凭据的流程；
- 最小只读角色或 Scope；
- 是否需要租户 ID、项目 ID、组织 ID 或区域标识；
- 凭据有效期、刷新方式以及失效错误码；
- 测试账号可访问的数据范围。

### 5.3 字段与脱敏

- 事件唯一标识、事件时间和规则名称字段；
- 风险等级及其枚举范围；
- 源/目的 IP、端口、协议和资产字段；
- 原始日志、证据、攻击状态和处置建议字段；
- 分页游标、总数、请求 ID 和平台错误字段；
- 哪些字段属于敏感信息，以及进入仓库、日志和测试证据前的脱敏要求；
- 至少一份不含敏感信息的成功响应样例、空结果样例和错误响应样例。

## 6. 最小适配位置

### 6.1 已确认的现有调度结构

基线代码已确认以下位置：

| 位置 | 主要对象 | 作用 |
|---|---|---|
| `src/sec_agent/tools/base.py` | `ToolDispatcher` | 唯一工具调度入口；根据 `tool_name` 分发请求 |
| `src/sec_agent/tools/base.py` | `unsupported_tool_result()` | 为未注册工具构造结构化失败结果 |
| `src/sec_agent/tools/tool_dispatcher.py` | `build_platform_tool_dispatcher()` | 集中注册五类工具并构建 `ToolDispatcher` |
| `src/sec_agent/tools/xdr_query_tool.py` | `handle_xdr_query()` | 当前内置 XDR 样例查询 handler |
| `src/sec_agent/platforms/fixed_sample.py` | `FixedSampleAdapter` | 固定告警样例和固定样例工具装配 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | JSONL 告警读取、标准化和样例工具装配 |
| `src/sec_agent/services/investigation.py` | `xdr_log_query` 调用 | 调查链通过现有工具契约发起 XDR 查询 |

`build_platform_tool_dispatcher()` 当前集中注册：

- `evidence_lookup`；
- `stateful_response_mock`；
- `response_verify`；
- `xdr_log_query`；
- `stateful_mock`。

未知工具由 `ToolDispatcher` 返回结构化结果：

- `status=FAILED`；
- `error_type=UNSUPPORTED_TOOL`；
- `retryable=true`；
- `external_side_effect=false`；
- `side_effect_type=NONE`。

### 6.2 当前内置 XDR Handler 边界

`src/sec_agent/tools/xdr_query_tool.py::handle_xdr_query()` 当前具有以下实际行为：

1. 不访问真实 XDR API；
2. 当前未使用 `request.params` 中的查询条件；
3. 每次固定返回一条内置 SQL 注入样例日志；
4. `raw_result_ref` 使用 `builtin://xdr-log-query/` 前缀；
5. 结果使用 `output_preview.records` 承载记录；
6. 返回 `status=SUCCESS`、`retryable=false`；
7. 返回 `external_side_effect=false`、`side_effect_type=READ_ONLY`。

因此，该能力只能标记为“内置固定样例”，不得标记为真实 XDR 查询或 JSONL 查询。

### 6.3 Fixed/JSONL 样例边界

`FixedSampleAdapter` 和 `JsonlSampleAdapter` 都通过 `build_platform_tool_dispatcher()` 获取现有唯一调度器，且当前均未通过 `extra_handlers` 覆盖 `xdr_log_query`，因此两者调用该工具时都会使用默认的内置 `handle_xdr_query()`。

需要区分三类数据：

| 数据入口 | 当前来源 | 说明 |
|---|---|---|
| `FixedSampleAdapter.fetch_alerts()` | 固定 WebShell 告警 | 返回固定告警记录和固定证据引用 |
| `JsonlSampleAdapter.fetch_alerts()` | JSONL 文件 | 读取并校验标准化或原始 JSONL 告警 |
| `handle_xdr_query()` | 内置 SQL 注入日志 | 独立的 MVP 内置 XDR 样例，不读取上述两类告警 |

这三类入口不能描述为同一份真实 XDR 数据。已有来源标识包括 `fixed_sample`、`jsonl_sample`、`fixed://`、`jsonl://` 和 `builtin://`；真实平台接入后必须使用可区分的新来源标识。

### 6.4 真实 XDR 最小接入方式

真实 XDR 查询必须沿用现有调用链：

```text
业务服务或 Agent
    -> 当前唯一工具调度器
    -> xdr_log_query 注册项
    -> XDR 只读适配器
    -> 真实 XDR API
    -> ToolResult
```

`build_platform_tool_dispatcher()` 已提供 `extra_handlers` 扩展点，并在默认工具注册完成后执行 `handlers.update(extra_handlers)`。因此，真实平台适配器可以通过同名 handler 覆盖默认 `xdr_log_query`，无需修改 `ToolDispatcher`：

```python
dispatcher = build_platform_tool_dispatcher(
    evidence_resolver=evidence_resolver,
    ledger=ledger,
    raw_result_prefix=raw_result_prefix,
    action_ref_prefix=action_ref_prefix,
    source_label="真实 XDR",
    extra_handlers={
        "xdr_log_query": real_xdr_handler,
    },
)
```

上述代码仅说明适配位置；接口、配置类和 `real_xdr_handler` 的具体实现必须在平台方确认 API 后确定。

接入约束如下：

1. 复用现有 `ToolRequest` 和 `ToolResult`，不新增一套平行工具契约。
2. 复用当前唯一工具调度器，不新建 `RealXdrDispatcher`、`XdrScheduler` 等第二入口。
3. 真实 XDR 访问逻辑放在平台适配层；业务 service 不直接依赖 XDR SDK 或 HTTP 地址。
4. 真实平台适配器通过 `extra_handlers` 显式覆盖 `xdr_log_query`；Fixed/JSONL 样例继续使用默认 handler。
5. 平台返回先完成校验和脱敏，再转换为标准输出字段。
6. 平台错误统一转换为结构化 `ToolResult`，不得把平台异常直接泄漏给前端。
7. 真实 handler 至少保持现有审计字段、`output_preview.records` 输出结构和只读副作用标记。
8. 真实结果使用区别于 `builtin://`、`fixed://` 和 `jsonl://` 的引用前缀，并提供可供前端和 Agent 判断的数据来源标识。

## 7. 无凭据配置模板

以下仅为候选配置项。最终名称应遵循仓库现有配置规范，并在取得真实接口说明后确认：

```dotenv
# 默认关闭真实平台调用，避免未配置环境误访问外部平台。
XDR_ENABLED=false

# 不填写真实内网地址或凭据。
XDR_BASE_URL=
XDR_API_VERSION=
XDR_AUTH_TYPE=
XDR_API_TOKEN=
XDR_TENANT_ID=

# 调用保护。
XDR_TIMEOUT_SECONDS=10
XDR_VERIFY_TLS=true

# fallback 必须显式开启，不能因真实平台失败自动伪装成功。
XDR_FALLBACK_ENABLED=false
```

安全要求：

- 真实凭据只通过受控环境变量或密钥管理服务注入；
- `.env.example`、Markdown、测试代码和 PR 描述中不得填写真实值；
- 日志中不得打印 Token、Secret、完整认证头或未脱敏平台响应；
- 配置缺失时返回结构化配置/鉴权错误，不默认访问固定样例并冒充真实数据。

## 8. 预期结构化返回

| 场景 | `status` | `error_type` | `retryable` | 数据/副作用要求 |
|---|---|---|---|---|
| 查询成功且有结果 | `SUCCESS` | 无 | `false` | 返回标准化预览和证据引用；标明真实 XDR 来源 |
| 查询成功但无结果 | `SUCCESS` | 无 | `false` | 返回空集合和匹配数量 0，不按异常处理 |
| 未知工具 | `FAILED` | `UNSUPPORTED_TOOL` | `true` | 不调用外部平台；上层可重新选择其他工具 |
| 参数校验失败 | `FAILED` | `VALIDATION` | `false` | 不调用外部平台；提示缺失或非法字段 |
| 鉴权失败 | `FAILED` | `AUTH` | `false` | 不输出凭据；默认不触发样例 fallback |
| 请求超时 | `FAILED` | `TIMEOUT` | `true` | 不产生外部副作用；是否重试由上层策略决定 |
| 平台不可达或服务异常 | `FAILED` | `PLATFORM_ERROR` | `true` | 保留脱敏后的平台状态和请求追踪信息 |
| 未识别异常 | `FAILED` | `UNKNOWN` | 按实际情况 | 返回统一摘要，不泄漏堆栈和敏感响应 |

所有只读 XDR 查询都应满足：

- `external_side_effect=false`；
- `side_effect_type=READ_ONLY`；
- 保留 `call_id`、`trace_id`、`event_id` 和 `idempotency_key`；
- 记录开始时间、结束时间、耗时和尝试次数；
- 不在 `error_message` 或 `output_preview` 中返回凭据。

## 9. 固定样例 fallback 边界

真实平台失败时不得静默返回固定样例并将其描述为真实平台结果。

仅在同时满足以下条件时允许使用固定样例 fallback：

1. 配置或调用参数明确启用 fallback；
2. 调用场景允许使用 Mock 或固定样例；
3. 返回结果明确标记 `fixed_sample`、`mock` 或等价来源；
4. 日志和审计结果保留真实平台失败的结构化原因；
5. 前端和 Agent 能够区分真实平台数据与固定样例；
6. fallback 不改变原调用的只读安全边界。

默认不触发 fallback 的场景：

- 鉴权失败或权限不足；
- 请求参数非法；
- 真实平台明确返回空结果；
- 调用方要求只接受真实平台数据；
- 无法保证样例来源标识能传递到最终消费者。

## 10. 接入验收清单

### 10.1 权限与环境

- [ ] 已获得测试环境 Base URL；
- [ ] 已确认 API 版本和接口文档；
- [ ] 已获得最小只读权限；
- [ ] 已确认鉴权方式及凭据轮换方式；
- [ ] 已确认网络、白名单、TLS 和代理要求；
- [ ] 已确认限流、分页、超时和时间格式。

### 10.2 字段与样例

- [ ] 已获得脱敏成功响应样例；
- [ ] 已获得空结果响应样例；
- [ ] 已获得鉴权失败、限流和平台错误样例；
- [ ] 已与标准告警字段映射文档对齐；
- [ ] 已确认敏感字段及日志脱敏规则。

### 10.3 代码与测试

- [ ] 真实适配器复用现有唯一工具调度入口；
- [ ] 未引入第二套调度器或平行工具契约；
- [ ] 配置模板不包含真实凭据；
- [ ] 成功、空结果、未知工具、鉴权失败、超时和不可达均有结构化测试；
- [ ] 真实平台和固定样例的来源标识可被前端和 Agent 识别；
- [ ] 目标测试和相关回归测试通过；
- [ ] PR 中不包含未脱敏平台数据。

## 11. 当前阻塞与协作项

| 协作对象 | 需要确认的内容 | 当前状态 |
|---|---|---|
| 主干收口负责人 | 最终联调候选 Commit | 已使用当前复测基线，后续如冻结 Commit 变化需更新 |
| 平台负责人 | 权限、接口、鉴权、网络和脱敏样例 | 待确认 |
| 字段映射负责人 | XDR 事件到标准告警契约的字段映射 | 待对齐 |
| Agent/调查链负责人 | 工具调用参数、错误消费和 fallback 边界 | 待对齐 |
| 前端负责人 | `real_xdr`、`fixed_sample` 等数据来源标识 | 待对齐 |

## 12. 当前结论

1. 现有平台工具调度器的两份目标测试已经在指定基线上通过，结果为 `6 passed in 0.13s`。
2. `xdr_log_query` 可作为真实 XDR 只读查询的现有接入点，无需新建第二套调度器。
3. 当前内置 XDR 记录仍是固定样例，不能标记为真实平台数据。
4. 接入工作的主要阻塞是平台权限、接口文档、鉴权方式、字段字典和脱敏样例尚未确认。
5. 获得上述信息后，可按本文定义的配置、适配和错误契约进入真实平台联调。
