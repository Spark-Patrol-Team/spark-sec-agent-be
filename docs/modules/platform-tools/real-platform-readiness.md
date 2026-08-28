# 2026-08-28 真实平台接入准备

## 结论

真实平台接入应落在平台适配层，不应把 XDR HTTP、鉴权、字段转换逻辑写入业务 service。

本轮已完成 `xdr_openapi` 接入边界、启动前配置检查、统一失败语义、固定样例降级开关和最小集成测试。当前仍不能声称真实平台已闭环，因为还缺 28 日实机 Base URL、只读凭据、真实响应样例、分页规则、AK/SK 签名串和一次可复现外部调用记录。

## 当前主链调用关系

入口关系如下：

1. `src/sec_agent/api/routes/events.py`
   - `POST /runs` 接收 `StartRunRequest`。
   - `PLATFORM_BACKEND=xdr_openapi` 时，请求来源应使用 `source=xdr`，进入同一条编排主链。

2. `src/sec_agent/api/deps.py`
   - 从 `app.state.container` 取运行时容器。

3. `src/sec_agent/bootstrap/container.py`
   - `build_container()` 读取 `Settings`。
   - `_build_platform()` 按 `PLATFORM_BACKEND` 创建平台适配器。
   - `PLATFORM_BACKEND=xdr_openapi` 时创建 `XdrOpenApiAdapter`。

4. `src/sec_agent/services/orchestrator.py`
   - `Orchestrator.start()` 创建 `trace_id/run_id`。
   - 进入 `AlertIngestService.ingest()`。
   - 接入失败时保留同一个 `trace_id`，状态置为 `FAILED`。
   - 如真实平台超时/不可达/空结果且显式允许降级，则继续主链，并在 `timeline/errors` 中标记“已降级到固定样例”。

5. `src/sec_agent/services/ingest.py`
   - 不再对 `source=xdr` 硬编码 `NotImplementedError`。
   - 统一调用 `PlatformAdapter.fetch_alerts()`。
   - 容器装配出的主链会校验请求来源与运行时平台后端，避免 `source=xdr` 被固定样例静默处理。

6. `src/sec_agent/platforms/xdr_openapi.py`
   - 真实 XDR OpenAPI 适配器边界。
   - 负责 HTTP 调用、鉴权头、超时、字段转换、空结果判断和降级触发。

7. `src/sec_agent/platforms/raw_jsonl.py`
   - 陈敏负责的 XDR 字段映射规则应优先沉淀在这里或复用这里的 `RawJsonlNormalizer`。
   - 真实返回字段稳定后，再补充 XDR 专用映射，不要让上层业务消费原始平台字段。

8. `src/sec_agent/tools/tool_dispatcher.py`
   - 现有 `ToolDispatcher` 继续作为调查、处置、验证工具调用入口。
   - 杨嘉琪负责的平台调用适配器应通过 `XdrOpenApiAdapter.run_tool()` 或 `build_platform_tool_dispatcher(extra_handlers=...)` 接入。
   - 工具调用必须保留 `trace_id`、`event_id` 和 `idempotency_key`。

## 配置方案

可提交到仓库的是变量名和默认边界，不可提交真实值。

| 配置项 | 用途 | 是否敏感 | 默认值 |
| --- | --- | --- | --- |
| `PLATFORM_BACKEND` | 平台后端选择：`fixed_sample` / `jsonl_sample` / `xdr_openapi` | 否 | `fixed_sample` |
| `XDR_BASE_URL` | XDR OpenAPI 基础地址 | 是 | 空 |
| `XDR_AUTH_TYPE` | 鉴权类型：`token` / `aksk` | 否 | `token` |
| `XDR_TOKEN` | Token 鉴权凭据 | 是 | 空 |
| `XDR_ACCESS_KEY` | AK/SK 鉴权访问键 | 是 | 空 |
| `XDR_SECRET_KEY` | AK/SK 鉴权密钥 | 是 | 空 |
| `XDR_ALERTS_PATH` | 告警查询路径 | 否 | `/api/v1/alerts` |
| `XDR_CONNECT_TIMEOUT_SECONDS` | 连接超时 | 否 | `5` |
| `XDR_READ_TIMEOUT_SECONDS` | 读取超时 | 否 | `30` |
| `XDR_STARTUP_CHECK` | 启动前配置检查 | 否 | `true` |
| `XDR_PREFLIGHT_HTTP_CHECK` | 启动前真实 HTTP 连通性探测 | 否 | `false` |
| `XDR_ALLOW_FIXED_SAMPLE_FALLBACK` | 是否允许固定样例降级 | 否 | `false` |

禁止进入 GitHub、GitLab、Gitee 或任何代码评审材料的内容：

- 真实 `XDR_BASE_URL`。
- `XDR_TOKEN`、`XDR_ACCESS_KEY`、`XDR_SECRET_KEY`。
- Cookie、联动码、账号密码、一次性验证码。
- 未脱敏平台返回、截图、真实内网 IP、主机名、原始 PCAP。

## 启动和切换条件

固定样例启动：

```bash
PLATFORM_BACKEND=fixed_sample uv run --python /opt/homebrew/bin/python3.11 python -m sec_agent.scripts.run_flow
```

JSONL 脱敏样例启动：

```bash
PLATFORM_BACKEND=jsonl_sample JSONL_INPUT_MODE=raw uv run --python /opt/homebrew/bin/python3.11 python -m sec_agent.scripts.run_flow
```

真实平台启动：

```bash
PLATFORM_BACKEND=xdr_openapi \
XDR_BASE_URL=<由本地 .env 或密钥系统注入> \
XDR_AUTH_TYPE=token \
XDR_TOKEN=<由本地 .env 或密钥系统注入> \
XDR_STARTUP_CHECK=true \
XDR_PREFLIGHT_HTTP_CHECK=false \
uv run --python /opt/homebrew/bin/python3.11 python -m uvicorn sec_agent.main:app --host 127.0.0.1 --port 8000
```

真实平台与固定样例 fallback 切换规则：

| 场景 | 默认主链状态 | 是否允许降级 |
| --- | --- | --- |
| 鉴权失败 `401/403` | `FAILED` | 不允许 |
| XDR 超时 | `FAILED` | 仅 `XDR_ALLOW_FIXED_SAMPLE_FALLBACK=true` 时允许 |
| XDR 不可达 | `FAILED` | 仅 `XDR_ALLOW_FIXED_SAMPLE_FALLBACK=true` 时允许 |
| XDR 空结果 | `FAILED` | 仅 `XDR_ALLOW_FIXED_SAMPLE_FALLBACK=true` 时允许 |
| 字段转换失败 | `FAILED` | 不允许 |
| 平台 5xx | `FAILED` | 仅 `XDR_ALLOW_FIXED_SAMPLE_FALLBACK=true` 时允许 |

## 失败处理约定

| 失败类型 | 主链状态 | `trace_id` | 前端展示 | 降级策略 |
| --- | --- | --- | --- | --- |
| 鉴权失败 | `FAILED` | 保留本次 `trace_id` | `errors[0].message` 展示 `auth` 和平台状态码 | 不降级，避免掩盖权限问题 |
| 超时/不可达 | 默认 `FAILED`；开启降级后继续主链 | 保留同一个 `trace_id` | `timeline[0]` 展示已降级，`errors` 展示原因 | 联调演示可降级 |
| 空结果 | 默认 `FAILED`；开启降级后继续主链 | 保留同一个 `trace_id` | `errors` 展示 `empty_result` | 联调演示可降级 |
| 字段转换失败 | `FAILED` | 保留本次 `trace_id` | `errors` 展示 `field_mapping` | 不降级，应修映射 |
| 请求来源与平台后端不匹配 | `FAILED` | 保留本次 `trace_id` | `errors` 展示“不匹配”和期望来源 | 不降级，应修启动配置或请求参数 |
| 工具不存在 | 调查链记录工具失败，必要时 `HUMAN_REQUIRED` | `ToolRequest/ToolResult` 保留 | 工具结果中展示 `unsupported_tool` | 不进入真实执行 |

## 最小集成测试

已新增 `tests/test_xdr_openapi_platform.py`，覆盖：

- 真实 XDR 适配器成功返回后继续进入现有主链，并停在高风险人工审批。
- 鉴权失败时主链进入 `FAILED`，且不降级。
- 超时时开启 `XDR_ALLOW_FIXED_SAMPLE_FALLBACK=true` 后可降级到固定样例，主链不卡死。
- 空结果未开启降级时进入 `FAILED`。
- 字段转换失败即使开启降级也进入 `FAILED`，避免污染字段契约。
- 启动前检查能拦截缺失 `XDR_BASE_URL` 和 `XDR_TOKEN`。
- `source=xdr` 必须配合 `PLATFORM_BACKEND=xdr_openapi`，不能被固定样例后端静默处理。

建议实机最小补测：

1. 使用只读凭据请求 1 条真实告警或安全事件。
2. 保存脱敏后的响应样例到联调证据目录，不提交原始响应。
3. 用该样例补 `XdrOpenApiAdapter._to_normalizer_raw()` 映射测试。
4. 用 `POST /runs` 发起 `{"source":"xdr","xdr_event_id":"<脱敏事件ID>"}`。
5. 验收 `trace_id`、`status`、`timeline`、`errors`、`triage`、`investigation.steps` 是否完整。

## 本轮验证记录

Python 版本：

```bash
uv run --python /opt/homebrew/bin/python3.11 python --version
```

结果：`Python 3.11.12`。

固定样例后端整链：

```bash
uv run --python /opt/homebrew/bin/python3.11 python -m sec_agent.scripts.run_flow
```

结果：

- 启动后进入 `APPROVAL_REQUIRED`。
- 本地审批后进入 `COMPLETED`。
- 时间线经过 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED -> EXECUTING -> VERIFYING -> COMPLETED`。

完整测试：

```bash
uv run --python /opt/homebrew/bin/python3.11 --with pytest --with httpx -m pytest -q
```

结果：`135 passed, 1 skipped`。

已知限制：

- 本轮按仓库规则未执行 Git 命令，因此未读取当前 HEAD，也未确认唯一候选 Commit。
- PR18 合入后的候选 Commit 需由负责人在允许执行 Git 的环境中确认，例如记录 `git rev-parse HEAD` 和 `git log -1 --oneline` 的输出。
- 当前 `aksk` 只完成配置边界隔离，HMAC 签名串需等真实平台文档或抓包记录确认后补齐。
- 当前真实告警路径默认 `/api/v1/alerts`，28 日联调时需按实机 OpenAPI 调整 `XDR_ALERTS_PATH`。
- 当前没有提交真实平台凭据、真实平台地址或未脱敏响应。

## T0828-06 状态更新：真实字段转换与下游交接

本节为 2026-08-28 追加内容，前述准备阶段记录继续保留。基于已取得的脱敏真实 Sangfor XDR 响应结构，`XdrOpenApiAdapter` 已完成真实告警列表响应到现有 `NormalizedAlertRecord`/`AlertRecord` 的字段转换，并覆盖分页、数组字段、秒/毫秒时间戳、目的资产回退、稳定 ID 跨页去重、缺字段、非法值和空结果处理。

仓库内可供复验的是脱敏结构示例 `tests/fixtures/xdr_contract/real_alert_records_sanitized.json`、对应模型/主链测试和完整运行命令；真实认证凭据、签名细节和原始响应仍只应存在于受控环境。下游任务应使用统一候选 Commit，先运行固定样例风险研判，再使用脱敏标准化记录进行字段对照，不应把脱敏值当作真实平台查询实体。

本分支验证结果：完整测试 **141 passed, 1 skipped**；固定 JSONL raw 主链已从 `RECEIVED` 运行至 `APPROVAL_REQUIRED`，审批后运行至 `COMPLETED`；真实记录示例已通过 `NormalizedAlertRecord`、`AlertRecord` 和 `AlertCorrelationService` 校验。

证据位置建议：
- 测试命令输出：联调记录或 CI 日志。
- 脱敏真实响应：联调证据目录，不提交原始敏感信息。
- 本仓库代码证据：`tests/test_xdr_openapi_platform.py`、`.env.example`、`src/sec_agent/platforms/xdr_openapi.py`。
