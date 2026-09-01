# 主链测试记录

## 0. 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 任务/测试批次 | 真实 XDR 告警输入接入后主链回归 |
| 执行人 | 李雨妍|
| 执行时间 | 2026-08-30；2026-08-31 |
| 基线分支与Commit | 当前工作区，包含真实 XDR 告警接入、签名实现和主链文档补充 |
| 环境 | macOS；Python 3.11；pytest；FastAPI TestClient；真实 XDR OpenAPI 联调环境 |
| 数据集/样例版本 | `tests/fixtures/fixed_alerts`；`fixed_sample` 内置样例；JSONL 样例；真实 XDR 告警 `alert-9fd0c034-ba09-4311-8360-cf1787206450` |
| 工作流/知识库版本 | 不适用，当前主链测试不依赖外部知识库 |
| 能力性质 | 自研代码；fixed_sample / jsonl_sample / xdr_openapi / Mock / fallback |
| 验收层级 | 回归 / 接口 / 集成 / 全链路 |
| 总体结论 | 阶段通过 |
| 关联正式交付章节 | docs/deliverables/测试方案与测试报告.md |

## 1. 测试范围与不在范围内事项

### 1.1 本轮覆盖

- 主链从 `POST /runs` 启动到 `APPROVAL_REQUIRED` 的接口路径。
- 审批通过后从 `APPROVAL_REQUIRED` 到 `COMPLETED` 的执行和验证路径。
- `fixed_sample` 主流程脚本路径。
- `jsonl_sample` 接入主链路径。
- `xdr_openapi` 通过官方联动码签名拉取真实 XDR 告警列表，并经 `/runs` 进入主链。
- XDR `uuId` 作为返回唯一标识的本地匹配逻辑。
- XDR 日志查询失败不阻断已命中真实告警进入审批的路径。
- 状态机合法迁移、非法迁移、审批拒绝和审批幂等。
- OpenAPI 生成结果与当前代码一致性。
- CORS 预检和实际接口响应。

### 1.2 本轮未覆盖

- 真实深信服 MCP 工具调用，原因是本轮只验证真实 XDR 告警输入，不验证真实调查工具闭环。
- XDR OpenAPI 全量接口，原因是本轮只验证 `POST /api/xdr/v1/alerts/list`。
- XDR 日志查询真实接口，原因是当前缺少日志查询接口路径、权限和返回结构完整契约。
- 真实高风险处置动作，原因是当前主链使用 Mock 处置工具。
- 真实 LLM deep agent 集成，原因是本地未配置 `LLM_API_KEY`，对应集成测试按预期跳过。
- MySQL 仓储真实数据库回归，原因是本轮未启动真实 MySQL 环境。

## 2. 前置条件与测试数据

- 前置条件：从仓库根目录执行；本地依赖已安装；真实 XDR 测试需要本地 `.env` 配置 `XDR_BASE_URL`、`XDR_AUTH_TYPE=auth_code`、`XDR_AUTH_CODE`、`XDR_ALERT_START_TIMESTAMP=1787155200`。
- 测试数据性质：固定样例 / JSONL 样例 / 真实 XDR 告警 / Mock 处置。
- 测试数据位置：`tests/fixtures/fixed_alerts`；`FixedSampleAdapter` 内置样例。

## 3. 真实执行命令

完整测试回归：

```text
PYTHONPATH=src /opt/homebrew/bin/python3.11 -m pytest -q
```

真实 XDR 接入相关局部回归：

```text
uv run pytest tests/test_xdr_openapi_platform.py tests/test_config.py tests/test_api_http.py -q
```

2026-08-31 ：

```text
env INVESTIGATION_BACKEND=tool_mock uv run pytest tests/test_xdr_openapi_platform.py tests/test_config.py tests/test_api_http.py tests/test_openapi_generation.py -q
```

已修改 Python 文件语法检查：

```text
uv run python -m py_compile src/sec_agent/platforms/xdr_openapi.py src/sec_agent/core/config.py src/sec_agent/bootstrap/container.py
```

主流程脚本：

```text
PYTHONPATH=src PLATFORM_BACKEND=fixed_sample /opt/homebrew/bin/python3.11 -m sec_agent.scripts.run_flow
```

OpenAPI 一致性检查：

```text
PYTHONPATH=src /opt/homebrew/bin/python3.11 -m sec_agent.scripts.generate_openapi
git diff --exit-code -- docs/swagger/openapi.json
```

HTTP 服务和接口联调：

```text
PYTHONPATH=src APP_ENV=test STORAGE_BACKEND=memory PLATFORM_BACKEND=fixed_sample INVESTIGATION_BACKEND=tool_mock CORS_ALLOWED_ORIGINS=http://frontend.test /opt/homebrew/bin/python3.11 -m uvicorn sec_agent.main:app --host 127.0.0.1 --port 18080
```

```text
curl -i -s -X OPTIONS 'http://127.0.0.1:18080/runs' -H 'Origin: http://frontend.test' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type'
```

```text
curl -s -X POST 'http://127.0.0.1:18080/runs' -H 'Content-Type: application/json' -H 'Origin: http://frontend.test' -d '{"source":"fixed_sample"}'
```

真实 XDR 告警输入联调：

```text
PLATFORM_BACKEND=xdr_openapi INVESTIGATION_BACKEND=tool_mock uv run uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
```

```text
curl -s -X POST 'http://127.0.0.1:8000/runs' \
  -H 'Content-Type: application/json' \
  -d '{"source":"xdr","xdr_event_id":"alert-9fd0c034-ba09-4311-8360-cf1787206450"}'
```

真实 XDR 联调只记录脱敏摘要，不记录真实联动码、真实平台地址和完整原始响应。

## 4. 测试用例与实际结果

| 用例ID | 优先级 | 类型 | 场景/输入 | 预期结果 | 实际结果 | 状态 | `trace_id` | 证据编号 | 缺陷编号 |
|---|---|---|---|---|---|---|---|---|---|
| MAIN-001 | P0 | 回归 | 执行完整 `pytest` | 全部测试通过，允许未配置 LLM 的集成测试跳过 | `73 passed, 1 skipped`；补充 CORS 8080 白名单后局部回归为 `74 passed, 1 skipped` | Pass | 无 | EVID-MAIN-001 | 无 |
| MAIN-002 | P0 | 全链路 | fixed_sample 执行 `run_flow` | 审批前 `APPROVAL_REQUIRED`，审批后 `COMPLETED` | 输出 `启动完成: status=APPROVAL_REQUIRED` 和 `审批后状态: status=COMPLETED` | Pass | 无 | EVID-MAIN-002 | 无 |
| MAIN-003 | P0 | 接口 | `POST /runs`，请求 `{"source":"fixed_sample"}` | 返回 `EventContext`，状态为 `APPROVAL_REQUIRED` | 生成事件 `evt-f0ce793e-4e47-4db2-afe4-ee3998d92505`，状态 `APPROVAL_REQUIRED` | Pass | `trace-09978e32-22a0-48e4-b066-8742371753c6` | EVID-MAIN-003 | 无 |
| MAIN-004 | P1 | 接口 | `GET /events/{event_id}` 查询 MAIN-003 事件 | 返回 200，并返回同一事件详情 | 返回 200，事件可查询，响应包含 CORS 头 | Pass | `trace-09978e32-22a0-48e4-b066-8742371753c6` | EVID-MAIN-004 | 无 |
| MAIN-005 | P1 | 安全/接口 | `OPTIONS /runs` CORS 预检 | 返回 200，允许配置的 origin | 返回 `HTTP/1.1 200 OK` 和 `access-control-allow-origin: http://frontend.test` | Pass | 无 | EVID-MAIN-005 | 无 |
| MAIN-006 | P1 | 文档/接口 | 生成 OpenAPI 并检查 diff | `docs/swagger/openapi.json` 与代码一致 | OpenAPI 接口数量 7，`git diff --exit-code` 无差异 | Pass | 无 | EVID-MAIN-006 | 无 |
| MAIN-007 | P1 | 集成 | jsonl_sample 样例进入主链 | 启动后进入审批，审批后完成 | 已由 `tests/test_jsonl_platform.py` 和 `tests/test_raw_jsonl_ingest_and_correlation.py` 覆盖 | Pass | 无 | EVID-MAIN-007 | 无 |
| MAIN-008 | P1 | 异常/状态 | 非法状态迁移 | 抛出 `InvalidStatusTransition` | 已由 `tests/test_state_flow.py` 覆盖 | Pass | 无 | EVID-MAIN-008 | 无 |
| MAIN-009 | P0 | 真实平台/全链路输入 | `POST /runs`，请求 `{"source":"xdr","xdr_event_id":"alert-9fd0c034-ba09-4311-8360-cf1787206450"}` | 后端通过 XDR OpenAPI 拉取真实告警，命中目标告警并进入审批 | 2026-08-31 续跑返回 `APPROVAL_REQUIRED`；`requested_source=xdr`；`effective_source=xdr_openapi`；`fallback_source=null`；`errors=[]`；`event_id=evt-fd481d29-7de4-41ef-9dc9-0635b0fb9458`；`run_id=run-c6a6d619-2569-475d-a20e-e00096955706` | Pass | `trace-9f3362df-49c6-4722-9b07-50448e6b7a3e` | EVID-MAIN-009 | 无 |
| MAIN-010 | P0 | 自动化回归 | 执行 `uv run pytest tests/test_xdr_openapi_platform.py tests/test_config.py tests/test_api_http.py -q`；2026-08-31 续跑加入 OpenAPI 一致性检查 | XDR 接入、配置读取、HTTP 主链和 OpenAPI 相关测试通过 | 2026-08-31 续跑 `34 passed in 0.52s` | Pass | 无 | EVID-MAIN-010 | 无 |
| MAIN-011 | P1 | 语法检查 | 执行已修改 Python 文件 `py_compile` | 文件可被 Python 正常编译 | 通过，无输出 | Pass | 无 | EVID-MAIN-011 | 无 |

## 5. 结果汇总

| 指标 | 数量 |
|---|---:|
| 通过 | 11 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 不适用 | 0 |
| 测试框架skipped（如有） | 1 |

- 关键状态时间线或输出摘要：样例审批闭环为 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED -> EXECUTING -> VERIFYING -> COMPLETED`；真实 XDR 告警输入联调到达 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED`。
- 实际调用的Agent、工具或fallback：fixed_sample、jsonl_sample、xdr_openapi、tool_mock、stateful_response_mock、内置或 OpenAPI `xdr_log_query` 工具；未配置真实 LLM 时 deep agent 真实集成测试跳过。
- 与预期不一致项：无。真实 MCP、真实日志查询接口和真实处置能力未覆盖，已列入未覆盖范围。

## 6. 指标贡献与原始计数

| 指标 | 计算口径 | 分子/原始计数 | 分母/原始计数 | 结果 | 数据或脚本证据 |
|---|---|---:|---:|---:|---|
| 主链测试通过率 | 本文列出的正式用例 Pass 数 / 正式用例总数 | 11 | 11 | 100% | EVID-MAIN-001 至 EVID-MAIN-011 |
| 自动化测试通过情况 | pytest 通过数 / pytest 已执行测试数，不含 skipped | 34 | 34 | 100% | EVID-MAIN-010 |
| CORS 预检通过情况 | 配置 origin 的预检请求成功数 / 本轮预检请求数 | 1 | 1 | 100% | EVID-MAIN-005 |

## 7. 证据索引

| 证据 | 位置 | 脱敏状态 | 支持的结论 |
|---|---|---|---|
| EVID-MAIN-001 | 本地命令输出：`PYTHONPATH=src /opt/homebrew/bin/python3.11 -m pytest -q` | 不含敏感信息 | 完整测试回归通过，真实 LLM 集成测试按预期跳过 |
| EVID-MAIN-002 | 本地命令输出：`python -m sec_agent.scripts.run_flow` | 不含敏感信息 | fixed_sample 主流程审批后可到 `COMPLETED` |
| EVID-MAIN-003 | 本地 HTTP 响应：`POST /runs` | 不含敏感信息 | 主链接口可生成测试事件 |
| EVID-MAIN-004 | 本地 HTTP 响应：`GET /events/{event_id}` | 不含敏感信息 | 事件详情可查询，CORS 实际响应生效 |
| EVID-MAIN-005 | 本地 HTTP 响应：`OPTIONS /runs` | 不含敏感信息 | CORS 预检通过 |
| EVID-MAIN-006 | 本地命令输出：OpenAPI 生成和 diff 检查 | 不含敏感信息 | 接口文档与代码一致 |
| EVID-MAIN-007 | `tests/test_jsonl_platform.py`；`tests/test_raw_jsonl_ingest_and_correlation.py` | 不含敏感信息 | JSONL 样例可进入主链 |
| EVID-MAIN-008 | `tests/test_state_flow.py` | 不含敏感信息 | 状态机合法、非法和审批路径受测 |
| EVID-MAIN-009 | 本地真实 XDR 联调脱敏输出：`POST /runs` + `xdr_event_id=alert-9fd0c034-ba09-4311-8360-cf1787206450`；2026-08-31 续跑 `event_id=evt-fd481d29-7de4-41ef-9dc9-0635b0fb9458`、`run_id=run-c6a6d619-2569-475d-a20e-e00096955706`、`trace_id=trace-9f3362df-49c6-4722-9b07-50448e6b7a3e`；状态线 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED`；错误列表为空 | 已脱敏，不含联动码、平台地址和原始响应 | 后端可从真实 XDR 拉取目标告警并进入 `APPROVAL_REQUIRED` |
| EVID-MAIN-010 | 本地命令输出：`env INVESTIGATION_BACKEND=tool_mock uv run pytest tests/test_xdr_openapi_platform.py tests/test_config.py tests/test_api_http.py tests/test_openapi_generation.py -q`；结果 `34 passed in 0.52s` | 不含敏感信息 | XDR 接入、配置读取、HTTP 主链和 OpenAPI 相关局部回归通过 |
| EVID-MAIN-011 | 本地命令输出：`uv run python -m py_compile ...` | 不含敏感信息 | 已修改 Python 文件语法检查通过 |

## 8. 失败项与已知限制

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| 真实 LLM 集成测试跳过 | 未配置 `LLM_API_KEY` 时运行完整 pytest | 不阻塞主链 Mock / 样例回归；阻塞真实 deep agent 验证 | 后续配置脱敏环境变量和真实工具后单独复验 |
| 真实 MCP 未接入 | 期望主链调用真实 MCP 调查工具 | 阻塞生产调查闭环 | 补齐 MCP 工具地址、鉴权、schema 和测试数据 |
| XDR OpenAPI 只验证告警列表接口 | 期望调用全量 XDR OpenAPI 能力 | 不阻塞真实告警输入；阻塞完整平台能力声明 | 补齐更多接口契约、错误码和联调样本 |
| XDR 日志查询接口未验收 | `xdr_log_query` 调用真实日志接口 | 不阻塞已命中告警进入审批；影响调查证据丰富度 | 索要日志接口路径、请求参数、返回结构和权限说明 |
| 真实高风险处置未接入 | 审批通过后期望真实封禁或隔离 | 阻塞生产处置动作 | 替换 Mock 工具并补审批、回滚、审计测试 |
| MySQL 模式未在本轮复验 | `STORAGE_BACKEND=mysql` 且连接真实数据库 | 不阻塞 memory 模式；影响持久化验收 | 准备数据库环境后补充回归 |

## 9. 验收结论

- 本轮可确认：当前后端可以通过现有 `POST /runs` 主链入口，从真实 XDR 告警列表接口拉取目标告警，并到达 `APPROVAL_REQUIRED`。
- 本轮仍不能确认：真实深信服 MCP 工具、XDR 日志查询真实接口、真实 LLM 调查闭环、真实高风险处置动作、MySQL 真实环境持久化。
- 是否影响上下游或主链：真实告警输入已可用；真实调查工具和生产处置能力仍需后续接入。
- 建议状态：已提交待验收。

## 10. 变更记录

| 日期 | 基线Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-26 | main / 5c05d61 | 新增主链测试记录文档，整理当前已执行回归、接口、CORS 和 OpenAPI 检查结果 | 阶段通过 |
| 2026-08-30 | 当前工作区 | 补充 XDR OpenAPI 告警接入单测、官方签名单测、真实告警输入联调记录和日志查询非阻断回归 | 阶段通过 |
| 2026-08-31 | 当前工作区 | 仅续跑真实 XDR `/runs` 主链输入，保存同一次运行的脱敏摘要、状态线和错误列表 | 阶段通过 |
