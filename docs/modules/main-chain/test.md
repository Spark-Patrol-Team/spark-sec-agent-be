# 主链测试记录

## 0. 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 任务/测试批次 | 主链文档补充前最近一次本地回归 |
| 执行人 | 李雨妍|
| 执行时间 | 2026-08-26 |
| 基线分支与Commit | main / 5c05d61，包含当前工作区未提交 CORS 白名单和文档补充 |
| 环境 | macOS；Python 3.11；pytest；FastAPI TestClient |
| 数据集/样例版本 | `tests/fixtures/fixed_alerts`；`fixed_sample` 内置样例；JSONL 样例 |
| 工作流/知识库版本 | 不适用，当前主链测试不依赖外部知识库 |
| 能力性质 | 自研代码；fixed_sample / jsonl_sample / Mock / fallback |
| 验收层级 | 回归 / 接口 / 集成 / 全链路 |
| 总体结论 | 阶段通过 |
| 关联正式交付章节 | docs/deliverables/测试方案与测试报告.md |

## 1. 测试范围与不在范围内事项

### 1.1 本轮覆盖

- 主链从 `POST /runs` 启动到 `APPROVAL_REQUIRED` 的接口路径。
- 审批通过后从 `APPROVAL_REQUIRED` 到 `COMPLETED` 的执行和验证路径。
- `fixed_sample` 主流程脚本路径。
- `jsonl_sample` 接入主链路径。
- 状态机合法迁移、非法迁移、审批拒绝和审批幂等。
- OpenAPI 生成结果与当前代码一致性。
- CORS 预检和实际接口响应。

### 1.2 本轮未覆盖

- 真实深信服 MCP / XDR OpenAPI 调用，原因是未配置真实平台地址、鉴权和字段映射。
- 真实高风险处置动作，原因是当前主链使用 Mock 处置工具。
- 真实 LLM deep agent 集成，原因是本地未配置 `LLM_API_KEY`，对应集成测试按预期跳过。
- MySQL 仓储真实数据库回归，原因是本轮未启动真实 MySQL 环境。

## 2. 前置条件与测试数据

- 前置条件：从仓库根目录执行；设置 `PYTHONPATH=src`；本地依赖已安装；未配置真实平台密钥。
- 测试数据性质：固定样例 / JSONL 样例 / Mock。
- 测试数据位置：`tests/fixtures/fixed_alerts`；`FixedSampleAdapter` 内置样例。

## 3. 真实执行命令

完整测试回归：

```text
PYTHONPATH=src /opt/homebrew/bin/python3.11 -m pytest -q
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

## 5. 结果汇总

| 指标 | 数量 |
|---|---:|
| 通过 | 8 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 不适用 | 0 |
| 测试框架skipped（如有） | 1 |

- 关键状态时间线或输出摘要：`RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED -> EXECUTING -> VERIFYING -> COMPLETED`。
- 实际调用的Agent、工具或fallback：fixed_sample、jsonl_sample、tool_mock、stateful_response_mock、内置 `xdr_log_query` 样例工具；未配置真实 LLM 时 deep agent 真实集成测试跳过。
- 与预期不一致项：无。真实平台能力未覆盖，已列入未覆盖范围。

## 6. 指标贡献与原始计数

| 指标 | 计算口径 | 分子/原始计数 | 分母/原始计数 | 结果 | 数据或脚本证据 |
|---|---|---:|---:|---:|---|
| 主链测试通过率 | 本文列出的正式用例 Pass 数 / 正式用例总数 | 8 | 8 | 100% | EVID-MAIN-001 至 EVID-MAIN-008 |
| 自动化测试通过情况 | pytest 通过数 / pytest 已执行测试数，不含 skipped | 73 | 73 | 100% | EVID-MAIN-001 |
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

## 8. 失败项与已知限制

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| 真实 LLM 集成测试跳过 | 未配置 `LLM_API_KEY` 时运行完整 pytest | 不阻塞主链 Mock / 样例回归；阻塞真实 deep agent 验证 | 后续配置脱敏环境变量和真实工具后单独复验 |
| 真实 XDR / MCP 未接入 | 使用真实 `source=xdr` 或真实平台字段联调 | 阻塞生产平台闭环 | 补齐平台适配器、鉴权、字段映射和测试数据 |
| 真实高风险处置未接入 | 审批通过后期望真实封禁或隔离 | 阻塞生产处置动作 | 替换 Mock 工具并补审批、回滚、审计测试 |
| MySQL 模式未在本轮复验 | `STORAGE_BACKEND=mysql` 且连接真实数据库 | 不阻塞 memory 模式；影响持久化验收 | 准备数据库环境后补充回归 |

## 9. 验收结论

- 本轮可确认：当前 main 的主链在 fixed_sample、jsonl_sample、HTTP 接口、CORS、OpenAPI 和状态机路径上阶段通过。
- 本轮不能确认：真实深信服 MCP / XDR OpenAPI、真实 LLM 调查闭环、真实高风险处置动作、MySQL 真实环境持久化。
- 是否影响上下游或主链：不影响当前 MVP 主链；真实平台和生产处置能力仍需后续接入。
- 建议状态：已提交待验收。

## 10. 变更记录

| 日期 | 基线Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-26 | main / 5c05d61 | 新增主链测试记录文档，整理当前已执行回归、接口、CORS 和 OpenAPI 检查结果 | 阶段通过 |
