# 平台工具模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 平台工具模块（Platform Tools） |
| 负责人 | 杨嘉琪 |
| 文档状态 | 已复验 |
| 实现状态 | 固定样例、JSONL 样例和 Mock 能力已实现并复验；真实 XDR 只读适配待实现 |
| 能力性质 | 自研代码、固定样例、Mock、fallback；真实平台能力未接通 |
| 关联任务/需求 | `T0826-07`、`T0827-05` |
| 关联正式交付章节 | 仓库系统开发与运行说明中的模块说明、配置与运行章节；具体章号待总文档负责人统一 |
| 对应 PR 或 Commit | 适用基线 `main@95defad5e6d8a44fdb601d844d876f25544f479d`；本文档 PR 待创建 |
| 适用代码版本 | `main@95defad5e6d8a44fdb601d844d876f25544f479d` |
| 最后更新时间 | 2026-08-28 |

## 1. 当前实现摘要

### 1.1 已实现

- 唯一 `ToolDispatcher` 及基于 handler 映射的统一分发。
- 五类工具注册：`evidence_lookup`、`xdr_log_query`、`stateful_mock`、`stateful_response_mock`、`response_verify`。
- 未知工具结构化错误：`FAILED / UNSUPPORTED_TOOL / retryable=true`。
- 固定 WebShell 告警样例及证据引用。
- 标准化/原始 JSONL 告警读取、Pydantic 校验和 `AlertRecord` 转换。
- 内置 XDR SQL 注入日志样例查询。
- 同一 ledger 或 session 生命周期内的有状态 Mock 和响应验证。
- `extra_handlers` 扩展点，可覆盖默认工具 handler。
- `ToolResult` 审计字段、错误字段、输出预览和副作用标记。

### 1.2 未实现或未复验

- 真实 XDR OpenAPI 调用、鉴权、分页、限流和字段映射尚未实现。
- XDR API Base URL、版本、最小只读权限和鉴权方式尚待平台方确认。
- 候选 XDR 配置项尚未写入正式配置模型；本文只提供无凭据建议模板。
- 真实平台的成功、空结果、鉴权失败、超时、限流和不可达响应尚未实测。
- MCP、FastGPT/OpenClaw 等真实平台能力尚未接入。
- 本轮没有执行最新主干全部 pytest，仅执行两份目标测试文件。

## 2. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/tools/base.py` | `ToolDispatcher` | 唯一工具调度入口，根据 `tool_name` 分发请求 |
| `src/sec_agent/tools/base.py` | `unsupported_tool_result()` | 构造未知工具结构化错误 |
| `src/sec_agent/tools/tool_dispatcher.py` | `build_platform_tool_dispatcher()` | 注册五类工具，合并 `extra_handlers` 并构建调度器 |
| `src/sec_agent/tools/xdr_query_tool.py` | `build_evidence_lookup_handler()` | 构造证据查询 handler |
| `src/sec_agent/tools/xdr_query_tool.py` | `handle_xdr_query()` | 返回内置 XDR SQL 注入样例日志 |
| `src/sec_agent/tools/stateful_mock_tool.py` | Stateful Mock handlers / ledger 协作 | 模拟会话状态、响应动作和验证 |
| `src/sec_agent/platforms/fixed_sample.py` | `FixedSampleAdapter` | 固定 WebShell 告警、证据解析和工具装配 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | JSONL 告警加载、校验、标准化和工具装配 |
| `src/sec_agent/platforms/raw_jsonl.py` | `RawJsonlNormalizer` | 原始 JSONL 到标准化记录的转换 |
| `src/sec_agent/platforms/mock_state.py` | `StatefulMockLedger` | Mock 状态保存与查询 |
| `src/sec_agent/services/investigation.py` | `xdr_log_query` 请求 | 调查链调用工具的上游位置 |
| `tests/test_tool_dispatcher_integration.py` | 调度器集成测试 | 主链工具、XDR 查询和未知工具错误验证 |
| `tests/test_mvp_tool.py` | MVP 工具测试 | 内置 XDR、状态合并和未知工具验证 |

## 3. 依赖与配置

| 名称 | 必需/可选 | 获取方式 | 未配置时行为 |
|---|---|---|---|
| Python `3.13.9` | 本轮复测必需 | 项目本地 `.venv` | 无法复现本轮环境 |
| Pydantic | 必需 | 项目依赖安装 | 模型导入或校验失败 |
| pytest | 测试必需 | 安装测试依赖 | 无法执行目标 pytest |
| `tzdata` | Windows 本地条件必需 | `.venv` 中通过 pip 安装 | 可能无法加载 `Asia/Shanghai` |
| 固定/JSONL 样例 | 样例模式必需 | 仓库 `tests/fixtures/` | 对应样例加载失败 |
| XDR Base URL/凭据 | 真实 XDR 模式必需，当前未配置 | 未来由受控环境变量或密钥管理服务注入 | 真实模式必须返回结构化配置或鉴权错误，不得冒充成功 |

- 支持的已复验环境：Windows、Python `3.13.9`、项目本地 `.venv`。
- Linux 服务端通常使用系统 IANA 时区数据，不受 Windows 本地缺少 `tzdata` 的问题影响。
- 敏感配置只通过环境变量或受控配置注入，不在文档、代码和样例中填写真实值。

候选无凭据配置模板见 `docs/modules/platform-tools/xdr-readonly-readiness.md`。变量名在平台接口和仓库配置规范确认前不视为正式配置契约。

## 4. 启动与调试

从仓库根目录执行目标复测：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_tool_dispatcher_integration.py tests/test_mvp_tool.py
```

- 本轮成功判据：`6 passed`，无 skipped、无 failed。
- 本轮实际结果：`6 passed in 0.13s`。
- 结果范围：仅包含上述两份测试文件，不代表最新主干全部 pytest。

Windows 出现以下错误时：

```text
zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Asia/Shanghai'
```

在项目虚拟环境安装：

```powershell
.\.venv\Scripts\python.exe -m pip install tzdata
```

该问题属于 Windows 本地开发环境依赖问题，不是业务代码缺陷。

## 5. 调用与接入方法

### 5.1 调用入口

- 平台 adapter 对外实现 `run_tool(request: ToolRequest) -> ToolResult`。
- `run_tool()` 将请求交给 adapter 持有的唯一 `ToolDispatcher`。
- `ToolDispatcher.dispatch()` 根据 `request.tool_name` 调用已注册 handler。
- 调查链通过 `src/sec_agent/services/investigation.py` 构造 `xdr_log_query` 请求。

### 5.2 最小示例

以下示例只展示契约，不包含真实凭据：

```python
request = ToolRequest(
    trace_id="trace-example",
    event_id="event-example",
    stage=BusinessStatus.INVESTIGATING,
    tool_name="xdr_log_query",
    action_name="query_log",
    params={},
    reason="查询事件关联日志",
    idempotency_key="event-example:xdr_log_query:1",
    risk_level=ToolRiskLevel.LOW,
)

result = platform.run_tool(request)
```

当前内置样例的关键返回：

```json
{
  "tool_name": "xdr_log_query",
  "status": "success",
  "summary": "已返回1条内置XDR样例日志",
  "raw_result_ref": "builtin://xdr-log-query/<call_id>",
  "output_preview": {
    "records": [
      {
        "rule_name": "STA-SQL注入攻击",
        "risk_level": "high"
      }
    ]
  },
  "retryable": false,
  "external_side_effect": false,
  "side_effect_type": "read_only"
}
```

### 5.3 真实 XDR 最小接入

真实平台 adapter 应提供符合 `Callable[[ToolRequest], ToolResult]` 的 handler，并复用现有扩展点：

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

该代码仅说明适配位置。真实接口、参数、配置类和 HTTP 实现必须在平台方提供正式文档和脱敏样例后确定。

### 5.4 上下游接入注意事项

- 保持现有 `ToolRequest`、`ToolResult` 和工具名不变。
- 不修改 Agent 的主要工具调用方式，不新增第二套调度入口。
- 真实 handler 至少保持 `output_preview.records`、审计字段和只读副作用标记。
- Fixed/JSONL 样例继续使用默认 `handle_xdr_query`；真实 adapter 显式覆盖。
- 真实、固定、JSONL 和内置样例必须使用可区分的数据来源标识。
- 空结果返回成功及空集合，不自动转为固定样例。

## 6. 异常处理与安全控制

- 输入错误：返回 `FAILED / VALIDATION / retryable=false`，不访问外部平台。
- 未知工具：返回 `FAILED / UNSUPPORTED_TOOL / retryable=true`，上层可重新选择其他工具。
- 鉴权失败：预期返回 `FAILED / AUTH / retryable=false`，不泄漏凭据，默认不 fallback。
- 超时：预期返回 `FAILED / TIMEOUT / retryable=true`，是否重试由上层策略决定。
- 平台不可达：预期返回 `FAILED / PLATFORM_ERROR / retryable=true`，保留脱敏平台状态。
- 重复调用与幂等：调用方必须提供 `idempotency_key`；只读调用无外部副作用。
- 权限、审批与敏感数据：真实查询使用最小只读权限；凭据不进入 Git、日志和返回体。
- 回滚：只读查询不需要业务回滚；未来真实状态变更工具必须另行设计审批和补偿。

## 7. 真实平台、Mock 与 fallback 边界

| 能力 | 当前实际实现 | 触发条件 | 不得误写为 |
|---|---|---|---|
| 固定告警读取 | 固定样例 | `FixedSampleAdapter.fetch_alerts()` | 真实 XDR 告警 |
| JSONL 告警读取 | 本地 JSONL 样例 | `JsonlSampleAdapter.fetch_alerts()` | 实时 XDR 查询 |
| `xdr_log_query` | 内置 SQL 注入日志样例 | 默认 handler | 真实 XDR 或 JSONL 查询 |
| `stateful_mock` | 内存 Mock | 调用对应工具 | 持久化平台状态 |
| `stateful_response_mock` | Mock 状态变化 | 调用对应工具 | 真实隔离、封禁或删除动作 |
| `response_verify` | Mock 动作验证 | 查询 ledger | 真实平台动作核验 |
| 真实 XDR 只读查询 | 未实现 | 取得接口、权限、鉴权和脱敏样例后 | 已接入能力 |
| 固定样例 fallback | 候选显式策略 | 调用模式允许且显式启用 | 真实平台成功结果 |

真实平台失败时不得静默返回样例并冒充成功。fallback 必须显式启用、保留真实失败原因并标明样例来源。

## 8. 已知限制与待办

| 优先级 | 事项 | 是否影响主链 | 负责人/完成条件 |
|---|---|---|---|
| P0 | 获取 XDR 只读权限、接口文档、鉴权方式和脱敏样例 | 不影响固定样例主链；阻塞真实接入 | 平台负责人提供，杨嘉琪对接 |
| P0 | 确认真实 XDR 字段与标准告警契约映射 | 不影响当前主链；阻塞真实数据标准化 | 字段映射负责人和杨嘉琪对齐 |
| P0 | 实现真实 `xdr_log_query` handler 及结构化错误 | 不影响当前主链；阻塞真实查询 | 平台条件就绪后实现和复验 |
| P1 | 补成功、空结果、鉴权、超时、限流和不可达测试 | 不影响当前主链 | 获得响应样例或可用测试环境 |
| P1 | 固化数据来源标识供前端和 Agent 消费 | 不影响当前主链；影响来源透明度 | 与前端、Agent 负责人确认 |
| P2 | 接入 MCP、FastGPT/OpenClaw | 否 | 后续按优先级推进 |

## 9. 运行观测、版本兼容与迁移

- 日志与关键指标位置：当前以 `ToolResult` 的状态、摘要、错误、平台状态、耗时和引用字段为主要观测证据；生产日志位置待部署方案确认。
- 健康检查或运行状态判断：目标测试通过可验证本地调度契约；真实平台健康检查尚未实现。
- 兼容的接口/Schema/平台版本：当前兼容基线中的 `ToolRequest` / `ToolResult`；XDR API 版本待平台方确认。
- 升级、迁移或回退注意事项：真实 handler 通过 `extra_handlers` 注入，关闭真实模式后应回到明确标源的固定样例模式；不得隐式切换来源。
- Windows 兼容：缺少 IANA 时区数据时在 `.venv` 安装 `tzdata`。

## 10. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-26 | `5defad5e6d8a44fdb601d844d876f25544f479d` | `T0826-07` 工具调度器复测和环境问题记录 | 两份目标测试共 6 项通过 |
| 2026-08-28 | `95defad5e6d8a44fdb601d844d876f25544f479d` | `T0827-05` 统一调度结构核查和 XDR 最小适配说明 | `test_tool_dispatcher_integration.py`、`test_mvp_tool.py` 共 6 项通过 |

