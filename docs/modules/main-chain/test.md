# 主链测试记录

## 0. 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | 主链 |
| 任务/测试批次 | 真实 XDR 告警输入接入后主链回归；Bridge 显式装配与安全边界优化；评测对比接口接入与 actual 结果包读取 |
| 执行人 | 李雨妍|
| 执行时间 | 2026-08-30；2026-08-31；2026-09-06；2026-09-07；2026-09-09；2026-09-11；2026-09-14 |
| 基线分支与Commit | PR #49本地集成候选；上游`main@24fd76e`，待形成最终提交 |
| 环境 | 历史macOS实机记录；本次Windows、Python 3.11、pytest、FastAPI TestClient |
| 数据集/样例版本 | `tests/fixtures/fixed_alerts`；`fixed_sample` 内置样例；JSONL 样例；真实 XDR 告警 `alert-9fd0c034-ba09-4311-8360-cf1787206450`；杨景凡 OFF/GUARDED A/B 结果包 |
| 工作流/知识库版本 | 评测对比使用正式`WSK-*`；脱敏元数据记录运行Commit`0eb38cc`、代码基线`7e4aad6`和模型`deepseek-v4-flash` |
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
- Bridge 与主链真实 Agent 接入显式装配：确认后续 Agent 接入边界为 `SecurityEvent + TriageResult -> Bridge -> InvestigationReport`，主链状态流不直接耦合具体 Agent。
- `Orchestrator` 可通过构造参数注入 Bridge，主链 `/runs` 路径可消费注入 Bridge 的调查报告。
- Bridge 安全边界：缺失或非法 `need_manual_takeover` 按 fail-closed 转人工，并保留 `manual_takeover_reason`。
- Bridge 证据来源保留：外部 Agent `evidence_source` 映射到主链 `evidence_sources`，用于区分知识引用、工具来源和事件证据。
- 评测汇总正式入口框架：通过 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 可替换正式评测汇总文件，失败定位到案例、知识模式和阶段。
- 评测对比 HTTP 接口：`GET /eval/comparisons` 返回 OFF/GUARDED 对比 Mock 数据，供前端评测对比页面先行接入。
- 评测对比证据分层：接口区分事件证据、工具查询结果和知识引用，并保留 `evidence_refs` 兼容字段。
- 评测对比 actual 包读取：通过 `EVAL_COMPARISON_FIXTURE_PATH` 读取正式 OFF/GUARDED 结果包目录、`_summary.json` 或已整理 JSON，要求至少 6 案，并自动生成 actual `summary`。
- 杨景凡正式 A/B 结果包实测：20 行运行汇总合并为 10 案 OFF/GUARDED 对比，输出 `data_source=actual`。
- 评测知识 ID 统一：历史 WebShell 知识 ID 展示口径已更新为正式 `WSK-*`，内部兼容历史输入映射。
- 状态机合法迁移、非法迁移、审批拒绝和审批幂等。
- OpenAPI 生成结果与当前代码一致性。
- CORS 预检和实际接口响应。

### 1.2 本轮未覆盖

- 真实深信服 MCP 工具在本轮 actual 评测接口变更中未重新跑全量主链调查，原因是本轮重点为结果包读取与汇总转换；服务器部署后需保留版本证据。
- XDR OpenAPI 全量接口，原因是本轮只验证 `POST /api/xdr/v1/alerts/list`。
- XDR 日志查询真实接口，原因是当前缺少日志查询接口路径、权限和返回结构完整契约。
- 真实高风险处置动作，原因是当前主链使用 Mock 处置工具。
- 真实 LLM deep agent 集成，原因是本轮主链装配优化不验证外部 LLM 服务和真实 MCP 工具闭环。
- FastGPT / 远程 Agent / 新 MCP Agent 真实 Bridge 实现，原因是平台原生直连 endpoint、鉴权和请求响应 Schema 尚未冻结。
- 正式 OFF/GUARDED 评测结果入库，原因是当前 `/eval/comparisons` 支持文件结果包读取但未接数据库。
- 逐案例耗时复现，原因是结果包未提供该字段，`duration_ms`保持0并明确标记。
- 项目组已依据20份实际报告形成逐案人工质量评分草案：GUARDED质量优胜3案、OFF优胜1案、同分6案，平均分5.8/8对5.7/8。可确认知识门禁行为10/10符合预期及case9的引用增益，但旧结果包不支持通用准确率或显著提升结论。该评分尚未转换为接口可加载的逐案结构化JSON，因此接口中的逐案`winner`继续保持未判定口径。
- MySQL 仓储真实数据库回归，原因是本轮未启动真实 MySQL 环境。

## 2. 前置条件与测试数据

- 前置条件：从仓库根目录执行；本地依赖已安装；真实 XDR 测试需要本地 `.env` 配置 `XDR_BASE_URL`、`XDR_AUTH_TYPE=auth_code`、`XDR_AUTH_CODE`、`XDR_ALERT_START_TIMESTAMP=1787155200`。
- 测试数据性质：固定样例 / JSONL 样例 / 真实 XDR 告警 / Mock 处置 / actual OFF-GUARDED 结果包。
- 测试数据位置：`tests/fixtures/fixed_alerts`；`FixedSampleAdapter` 内置样例；本地外部结果包目录 `T0905-07-杨景凡-OFF-GUARDED-AB结果包`，完整 `report_*.json` 不进入仓库。

## 3. 真实执行命令

完整测试回归：

```text
python -m pytest -q
```

结果：

```text
391 passed, 1 skipped, 1 warning
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

评测对比接口局部回归：

```text
/opt/homebrew/bin/python3.11 -m pytest tests/test_api_http.py tests/test_knowledge_evaluation_summary_schema.py -q
```

结果：

```text
20 passed in 0.62s
```

杨景凡 actual 结果包接口转换实测：

```text
EVAL_COMPARISON_FIXTURE_PATH=/Users/waiwaiwai/Desktop/AI+安全智能体项目文档/T0905-07-杨景凡-OFF-GUARDED-AB结果包 \
  /opt/homebrew/bin/python3.11 - <<'PY'
from fastapi.testclient import TestClient
from sec_agent.api.app import create_app
from sec_agent.bootstrap.container import build_container
from sec_agent.core.config import Settings

client = TestClient(create_app(container=build_container(Settings(
    app_env="test",
    storage_backend="memory",
    platform_backend="fixed_sample",
    investigation_backend="tool_mock",
))))
payload = client.get("/eval/comparisons").json()
print(payload["data_source"], payload["summary"], payload["results"][8]["guarded"]["matched_knowledge_ids"])
PY
```

结果：

```text
data_source=actual
comparison_id=cmp-20260911-yjf-off-guarded-ab
summary.total_cases=10
summary.guarded_wins=0
summary.off_wins=0
summary.ties=10
summary.manual_takeovers=10
case9.guarded.matched_knowledge_ids=["WSK-010","WSK-001","WSK-015"]
run_metadata.run_commit=0eb38cc
run_metadata.model=deepseek-v4-flash
human_review.status=pending
```

这里的`guarded_wins=0/off_wins=0/ties=10`表示“接口尚未载入逐案胜负”，不是人工复核认为两组效果相同。项目组人工质量评分草案为GUARDED优胜3案、OFF优胜1案、同分6案；平均分仅相差0.1/8，因此不宣称通用准确率或显著提升。详见`../scenario-knowledge/OFF-GUARDED人工评分表-2026-09-14.md`。

历史服务器Docker启动与actual接口验收（修复前分支，仅证明部署路径，不作为最终接口口径）：

```text
部署镜像：spark-sec-agent-be:manual-20260914-actual-eval
镜像 ID 前缀：60eecbd96c66
容器 ID 前缀：e00dacbde25c
备份时间戳：20260914145410
结果包挂载：/app/eval_results/spark-eval-actual-package
健康检查：GET /health -> status=ok, app_env=prod, storage_backend=mysql, platform_backend=xdr_openapi
评测接口：GET /eval/comparisons -> HTTP 200, content-length=27029
actual摘要（旧自动判定）：data_source=actual, total_cases=10, guarded_wins=1, off_wins=0, ties=9, manual_takeovers=10
case9知识命中：WSK-010, WSK-001, WSK-015
run_metadata.run_commit=null（本次修复已更正，服务器尚未重新部署）
```

fixed_sample 固定样例回退复验：

```text
env LLM_API_KEY= LLM_BASE_URL= PLATFORM_BACKEND=fixed_sample INVESTIGATION_BACKEND=tool_mock PYTHONPATH=src \
  /opt/homebrew/bin/python3.11 -m sec_agent.scripts.run_flow
```

结果：

```text
启动完成: event_id=evt-b30774f3-3d17-4365-ac8a-d2e2042fefc3, status=APPROVAL_REQUIRED
审批后状态: event_id=evt-b30774f3-3d17-4365-ac8a-d2e2042fefc3, status=COMPLETED
状态时间线: RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED -> EXECUTING -> VERIFYING -> COMPLETED
```

最新main集成检查：

```text
git fetch origin main feature/mainline-eval-summary-contract
git merge --no-commit --no-ff origin/main
python -m pytest -q
```

结论：

```text
上游main=24fd76e
已解决场景知识测试文档和DeepAgentBridge测试冲突。
保留main中的三档门禁、域外报告清洗、response_evidence_scope和研判合同。
保留PR #49独有的/eval/comparisons、WSK输出、证据分层、运行元数据和人工Review入口。
补齐case6域外结论清洗后全量回归：391 passed, 1 skipped, 1 warning。
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

Bridge 装配实现检查：

```text
检查范围：docs/modules/main-chain/design.md、development.md、test.md
检查结论：装配边界已写入主链三文档；本轮已落地显式 Bridge 注入；不新增 fixture，不新增其他模块文档。
```

Bridge 显式装配局部回归：

```text
uv run pytest tests/test_deep_agent_bridge.py tests/test_state_flow.py tests/test_api_http.py -q
```

结果：

```text
15 passed in 1.45s
```

Bridge 安全边界与接口局部回归：

```text
uv run pytest tests/test_deep_agent_bridge.py tests/test_investigation_and_dispatcher_integration.py tests/test_api_http.py tests/test_config.py tests/test_openapi_generation.py -q
```

结果：

```text
30 passed in 0.99s
```

评测汇总入口框架：

```text
uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q
```

结果：

```text
4 passed in 0.01s
```

显式指定正式汇总路径的入口复验：

```text
KNOWLEDGE_EVALUATION_SUMMARY_PATH=tests/fixtures/evaluation/minimal_knowledge_evaluation_summary.json \
  uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q
```

结果：

```text
4 passed in 0.02s
```

已修改主链装配文件语法检查：

```text
uv run python -m py_compile src/sec_agent/services/investigation.py src/sec_agent/services/orchestrator.py src/sec_agent/bootstrap/container.py
```

结果：通过，无输出。

2026-09-11 Bridge 安全边界语法检查：

```text
uv run python -m py_compile src/sec_agent/domain/models.py src/sec_agent/services/deep_agent_bridge.py src/sec_agent/api/presenters.py
```

结果：通过，无输出。

## 4. 测试用例与实际结果

| 用例ID | 优先级 | 类型 | 场景/输入 | 预期结果 | 实际结果 | 状态 | `trace_id` | 证据编号 | 缺陷编号 |
|---|---|---|---|---|---|---|---|---|---|
| MAIN-001 | P0 | 回归 | 在最新main集成候选执行完整`pytest` | 全部非外部依赖测试通过；真实LLM集成测试按配置缺失跳过 | 2026-09-14 Windows复验`391 passed, 1 skipped, 1 warning` | Pass | 无 | EVID-MAIN-001 | 无 |
| MAIN-002 | P0 | 全链路 | fixed_sample 执行 `run_flow` | 审批前 `APPROVAL_REQUIRED`，审批后 `COMPLETED` | 输出 `启动完成: status=APPROVAL_REQUIRED` 和 `审批后状态: status=COMPLETED` | Pass | 无 | EVID-MAIN-002 | 无 |
| MAIN-003 | P0 | 接口 | `POST /runs`，请求 `{"source":"fixed_sample"}` | 返回 `EventContext`，状态为 `APPROVAL_REQUIRED` | 生成事件 `evt-f0ce793e-4e47-4db2-afe4-ee3998d92505`，状态 `APPROVAL_REQUIRED` | Pass | `trace-09978e32-22a0-48e4-b066-8742371753c6` | EVID-MAIN-003 | 无 |
| MAIN-004 | P1 | 接口 | `GET /events/{event_id}` 查询 MAIN-003 事件 | 返回 200，并返回同一事件详情 | 返回 200，事件可查询，响应包含 CORS 头 | Pass | `trace-09978e32-22a0-48e4-b066-8742371753c6` | EVID-MAIN-004 | 无 |
| MAIN-005 | P1 | 安全/接口 | `OPTIONS /runs` CORS 预检 | 返回 200，允许配置的 origin | 返回 `HTTP/1.1 200 OK` 和 `access-control-allow-origin: http://frontend.test` | Pass | 无 | EVID-MAIN-005 | 无 |
| MAIN-006 | P1 | 文档/接口 | 生成 OpenAPI 并检查接口路径 | `docs/swagger/openapi.json` 与代码一致 | OpenAPI 接口数量 9，包含 `/eval/comparisons`，局部回归通过 | Pass | 无 | EVID-MAIN-006 | 无 |
| MAIN-007 | P1 | 集成 | jsonl_sample 样例进入主链 | 启动后进入审批，审批后完成 | 已由 `tests/test_jsonl_platform.py` 和 `tests/test_raw_jsonl_ingest_and_correlation.py` 覆盖 | Pass | 无 | EVID-MAIN-007 | 无 |
| MAIN-008 | P1 | 异常/状态 | 非法状态迁移 | 抛出 `InvalidStatusTransition` | 已由 `tests/test_state_flow.py` 覆盖 | Pass | 无 | EVID-MAIN-008 | 无 |
| MAIN-009 | P0 | 真实平台/全链路输入 | `POST /runs`，请求 `{"source":"xdr","xdr_event_id":"alert-9fd0c034-ba09-4311-8360-cf1787206450"}` | 后端通过 XDR OpenAPI 拉取真实告警，命中目标告警并进入审批 | 2026-08-31 续跑返回 `APPROVAL_REQUIRED`；`requested_source=xdr`；`effective_source=xdr_openapi`；`fallback_source=null`；`errors=[]`；`event_id=evt-fd481d29-7de4-41ef-9dc9-0635b0fb9458`；`run_id=run-c6a6d619-2569-475d-a20e-e00096955706` | Pass | `trace-9f3362df-49c6-4722-9b07-50448e6b7a3e` | EVID-MAIN-009 | 无 |
| MAIN-010 | P0 | 自动化回归 | 执行 `uv run pytest tests/test_xdr_openapi_platform.py tests/test_config.py tests/test_api_http.py -q`；2026-08-31 续跑加入 OpenAPI 一致性检查 | XDR 接入、配置读取、HTTP 主链和 OpenAPI 相关测试通过 | 2026-08-31 续跑 `34 passed in 0.52s` | Pass | 无 | EVID-MAIN-010 | 无 |
| MAIN-011 | P1 | 语法检查 | 执行已修改 Python 文件 `py_compile` | 文件可被 Python 正常编译 | 通过，无输出 | Pass | 无 | EVID-MAIN-011 | 无 |
| MAIN-012 | P0 | 文档/设计 | Bridge 与主链真实 Agent 接入装配设计 | 主链三文档内明确装配边界、配置选择、后续落地步骤和未覆盖范围 | 已写入 `design.md`、`development.md`、`test.md`；不新增其他目录文件 | Pass | 无 | EVID-MAIN-012 | 无 |
| MAIN-013 | P0 | 单元/集成 | 主链通过构造参数注入 Bridge 后执行 `POST /runs` 等价路径 | `Orchestrator` 调用注入 Bridge，并继续推进到 `APPROVAL_REQUIRED` | `tests/test_deep_agent_bridge.py` 新增注入 Bridge 用例；局部回归 `15 passed in 1.45s` | Pass | 无 | EVID-MAIN-013 | 无 |
| MAIN-014 | P0 | 评测入口 | 使用默认最小 fixture 与显式 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 跑评测汇总入口 | Schema、fixture 和正式入口框架通过；失败可定位到 `case_id`、`knowledge_mode`、`stage` | 默认入口 `4 passed in 0.01s`；显式路径入口 `4 passed in 0.02s` | Pass | 无 | EVID-MAIN-014 | 无 |
| MAIN-015 | P0 | 接口/评测 | `GET /eval/comparisons` | 返回 OFF/GUARDED 对比数据，包含 `schema_version`、`comparison_id`、`data_source`、`suite`、`summary`、`results` | 返回 `data_source=mock_fixture`、`suite.baseline=OFF`、`suite.candidate=GUARDED`；接口与 OpenAPI 回归通过 | Pass | 无 | EVID-MAIN-015 | 无 |
| MAIN-016 | P0 | 接口/评测 | `GET /eval/comparisons` 证据分层 | `off` 和 `guarded` 均区分事件证据、工具查询结果和知识引用 | 响应包含 `evidence_breakdown.event_evidence_refs`、`tool_result_refs`、`knowledge_refs`；默认 Mock 和正式包路径均通过断言 | Pass | 无 | EVID-MAIN-016 | 无 |
| MAIN-017 | P0 | 接口/评测 | 配置 `EVAL_COMPARISON_FIXTURE_PATH` 指向正式结果包 | 读取正式 JSON 包或结果包目录，至少 6 案，自动生成 actual `summary`；少于 6 案拒绝 | 临时 6 案 actual 结果包返回 `data_source=actual`、`summary.total_cases=6`；临时 1 案包返回 500 且提示至少 6 案 | Pass | 无 | EVID-MAIN-017 | 无 |
| MAIN-018 | P0 | Bridge/安全 | 外部 Agent 报告缺失或非法 `need_manual_takeover` | Bridge 按 fail-closed 转人工，并保留人工接管原因 | `test_bridge_fails_closed_when_manual_takeover_field_missing` 与 `test_bridge_fails_closed_when_manual_takeover_field_is_invalid` 通过 | Pass | 无 | EVID-MAIN-018 | 无 |
| MAIN-019 | P0 | Bridge/证据 | 外部 Agent 报告包含 `evidence_source` | 主链保留为 `InvestigationReport.evidence_sources`，详情视图暴露字段 | `test_deep_agent_backend_maps_external_report_to_domain_report` 与 HTTP view 字段断言通过 | Pass | 无 | EVID-MAIN-019 | 无 |
| MAIN-020 | P0 | 接口/评测 | `EVAL_COMPARISON_FIXTURE_PATH`指向杨景凡OFF/GUARDED A/B结果包目录 | 20行汇总合并为10案actual对比；读取脱敏运行元数据；未加载人工Review时不自动判优胜 | 返回`data_source=actual`、10案、`guarded_wins=0`、`ties=10`、`manual_takeovers=10`；`run_commit=0eb38cc`、模型`deepseek-v4-flash`；case9命中`WSK-010/001/015`；Review为`pending` | Pass | 无 | EVID-MAIN-020 | 无 |
| MAIN-021 | P0 | 部署/接口 | 服务器部署 `spark-sec-agent-be:manual-20260914-actual-eval` 后访问公网 `/health` 与 `/eval/comparisons` | 服务健康；评测接口返回 actual 10 案汇总 | `/health` 返回 `status=ok`、`app_env=prod`、`storage_backend=mysql`、`platform_backend=xdr_openapi`；`/eval/comparisons` 返回 HTTP 200、27029 字节、`data_source=actual`、10 案汇总 | Pass | 无 | EVID-MAIN-021 | 无 |
| MAIN-022 | P0 | 启动/回退 | Docker 服务启动与 fixed_sample 固定样例回退 | Docker 服务可启动；fixed_sample 主流程审批后完成 | 服务器容器 `e00dacbde25c` 健康；本地 `run_flow` 输出 `APPROVAL_REQUIRED -> COMPLETED` 完整状态线 | Pass | 无 | EVID-MAIN-022 | 无 |
| MAIN-023 | P0 | 集成 | 将PR #49叠加到`main@24fd76e` | 解决文本冲突，保留主干正式合同和PR #49独有增量，并完成统一回归 | 两处冲突已解决；最新门禁、域外报告、响应范围与评测接口共存；全量`391 passed, 1 skipped` | Pass | 无 | EVID-MAIN-023 | 无 |
| MAIN-024 | P1 | 启动/环境 | Windows 启动复验 | 在 Windows 环境启动后访问健康检查 | 当前执行环境为 macOS，缺少 Windows 主机或 Windows runner，不能做实机复验；已登记为环境不适用，需 Windows 环境补测 | N/A | 无 | EVID-MAIN-024 | 无 |

## 5. 结果汇总

| 指标 | 数量 |
|---|---:|
| 通过 | 23 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 不适用 | 1 |
| 测试框架skipped（如有） | 1 |

- 关键状态时间线或输出摘要：样例审批闭环为 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED -> EXECUTING -> VERIFYING -> COMPLETED`；真实 XDR 告警输入联调到达 `RECEIVED -> CORRELATING -> TRIAGED -> INVESTIGATING -> DECISION_READY -> APPROVAL_REQUIRED`。
- 实际调用的Agent、工具或fallback：fixed_sample、jsonl_sample、xdr_openapi、tool_mock、stateful_response_mock、内置或 OpenAPI `xdr_log_query` 工具、注入式 `DeepAgentBridge` 替身；本轮服务器部署验证 `/eval/comparisons` actual 结果包读取，不验证外部 LLM 服务和真实 MCP 工具闭环。
- 与预期不一致项：无。真实日志查询接口、真实处置能力、MySQL 真实环境持久化和 FastGPT / 远程 Agent Bridge 实现未覆盖，已列入未覆盖范围。

## 6. 指标贡献与原始计数

| 指标 | 计算口径 | 分子/原始计数 | 分母/原始计数 | 结果 | 数据或脚本证据 |
|---|---|---:|---:|---:|---|
| 主链测试通过率 | 本文列出的正式用例 Pass 数 / 已执行适用用例总数 | 23 | 23 | 100% | EVID-MAIN-001 至 EVID-MAIN-023 |
| 自动化测试通过情况 | pytest 通过数 / pytest 已执行非跳过测试数 | 213 | 213 | 100% | EVID-MAIN-001 |
| CORS 预检通过情况 | 配置 origin 的预检请求成功数 / 本轮预检请求数 | 1 | 1 | 100% | EVID-MAIN-005 |
| 环境不适用项 | 当前机器不可执行的环境专项 / 全部环境专项 | 1 | 1 | Windows 启动需另行复验 | EVID-MAIN-024 |

## 7. 证据索引

| 证据 | 位置 | 脱敏状态 | 支持的结论 |
|---|---|---|---|
| EVID-MAIN-001 | Windows本地命令输出：`python -m pytest -q`；结果`391 passed, 1 skipped, 1 warning` | 不含敏感信息 | 最新main集成候选完整非外部依赖回归通过；真实LLM集成测试因未提供有效配置跳过 |
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
| EVID-MAIN-012 | 主链文档：`docs/modules/main-chain/design.md`、`development.md`、`test.md` | 不含敏感信息 | Bridge 与主链真实 Agent 接入装配设计已收敛在主链三文档 |
| EVID-MAIN-013 | 本地命令输出：`uv run pytest tests/test_deep_agent_bridge.py tests/test_state_flow.py tests/test_api_http.py -q`；结果 `15 passed in 1.45s` | 不含敏感信息 | Bridge 显式注入、主链状态流和 HTTP 主链回归通过 |
| EVID-MAIN-014 | 本地命令输出：`uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q`；结果 `4 passed in 0.01s`。显式路径入口：`KNOWLEDGE_EVALUATION_SUMMARY_PATH=tests/fixtures/evaluation/minimal_knowledge_evaluation_summary.json uv run pytest tests/test_knowledge_evaluation_summary_schema.py -q`；结果 `4 passed in 0.02s` | 不含敏感信息 | 评测汇总入口框架已就绪，可在正式汇总形成后替换输入文件 |
| EVID-MAIN-015 | 本地命令输出：`uv run pytest tests/test_api_http.py tests/test_openapi_generation.py -q`；结果 `10 passed in 0.92s`；OpenAPI 生成输出 `接口数量: 9` | 不含敏感信息 | `GET /eval/comparisons` 可返回 OFF/GUARDED 对比数据，并已进入 OpenAPI |
| EVID-MAIN-016 | `tests/test_api_http.py::ApiHttpTest::test_eval_comparisons_returns_off_guarded_mock_payload` | 不含敏感信息 | 默认 Mock 响应已区分事件证据、工具查询结果和知识引用 |
| EVID-MAIN-017 | `tests/test_api_http.py::ApiHttpTest::test_eval_comparisons_reads_actual_result_package_and_builds_summary`；`test_eval_comparisons_rejects_incomplete_actual_fixture` | 不含敏感信息 | `EVAL_COMPARISON_FIXTURE_PATH` 结果包目录读取、至少 6 案校验和 actual summary 生成链路通过 |
| EVID-MAIN-018 | `tests/test_deep_agent_bridge.py::DeepAgentBridgeTest::test_bridge_fails_closed_when_manual_takeover_field_missing`；`test_bridge_fails_closed_when_manual_takeover_field_is_invalid` | 不含敏感信息 | Bridge 对外部 Agent 人工接管字段缺失/非法执行 fail-closed |
| EVID-MAIN-019 | `tests/test_deep_agent_bridge.py::DeepAgentBridgeTest::test_deep_agent_backend_maps_external_report_to_domain_report`；`tests/test_api_http.py::ApiHttpTest::test_event_http_flow_reaches_completed_after_approval` | 不含敏感信息 | 主链保留 `evidence_sources`，详情视图暴露证据来源字段和人工接管原因字段 |
| EVID-MAIN-020 | 本地命令输出：`EVAL_COMPARISON_FIXTURE_PATH=...T0905-07-杨景凡-OFF-GUARDED-AB结果包 /opt/homebrew/bin/python3.11 - <<'PY' ...` | 不记录完整 `report_*.json`，不含凭据；完整工具输出仅在本地结果包内 | 杨景凡正式 A/B 结果包已接入 `/eval/comparisons`：10 案 actual 汇总，case9 命中 `WSK-010/WSK-001/WSK-015`，运行 Commit 缺失按 `null` 记录 |
| EVID-MAIN-021 | 公网 HTTP 响应：`GET http://124.221.234.124:8080/health` 与 `GET http://124.221.234.124:8080/eval/comparisons` | 不含敏感信息；只记录汇总摘要，不记录服务器 `.env` | 服务器实际部署后服务健康，评测接口返回 actual 10 案汇总 |
| EVID-MAIN-022 | 服务器部署记录和本地命令输出：Docker 容器 `e00dacbde25c` 健康；`run_flow` 输出 `APPROVAL_REQUIRED -> COMPLETED` | 不含敏感信息 | Docker 启动与 fixed_sample 固定样例回退均通过 |
| EVID-MAIN-023 | 本地集成记录：PR #49头与`main@24fd76e`合并、冲突解决及全量回归 | 不含敏感信息 | PR #49独有评测增量可与主干正式门禁、域外报告和响应合同共存 |
| EVID-MAIN-024 | 本机环境说明：当前执行环境为 macOS，无 Windows 主机或 Windows runner | 不含敏感信息 | Windows 启动未在当前环境实机验证，需 Windows 环境补测 |

## 8. 失败项与已知限制

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| 真实 LLM 集成未复验 | 本轮主链装配优化不启动外部 LLM 服务 | 不阻塞主链 Mock / 样例回归；阻塞真实 deep agent 验证 | 后续配置脱敏环境变量和真实工具后单独复验 |
| 真实 MCP 服务器主链复验未完成 | 期望主链调用真实 MCP 调查工具 | 阻塞生产调查闭环最终验收 | 使用受控 `MCP_URLS`、`LLM_*` 和服务器 `.env` 完成部署后实机复验 |
| FastGPT / 远程 Agent Bridge 未实现 | 期望通过同一 Bridge 契约替换不同真实 Agent | 不影响当前主链；影响后续多 Agent 接入范围 | 平台方冻结 endpoint、鉴权和请求响应 Schema 后，在现有 `InvestigationBridge` 协议下新增适配实现和集成测试 |
| `/eval/comparisons` 未接数据库 | 期望返回入库后的正式 OFF/GUARDED 评测结果 | 不影响前端页面和正式 JSON 包先行对接；影响长期归档查询 | 正式 fixture 稳定后从文件读取升级为存储读取，并补数据源契约测试 |
| 逐案结构化人工Review尚未随结果包加载 | 已有项目组逐案人工质量评分草案，但接口仍缺少机器可读的逐案记录 | 不影响知识门禁10/10及case9引用增益结论；阻止接口把评分草案或能力通过率伪装成准确率 | 项目负责人确认评分表后再转换为`_human_review.json`；此前接口逐案胜负保持未判定 |
| 结果包逐案例耗时未提供 | 期望展示每案耗时 | 不影响对比摘要；影响耗时统计准确性 | 当前 `duration_ms=0`，并在 `run_metadata.key_config_notes` 说明未提供，不补造 |
| XDR OpenAPI 只验证告警列表接口 | 期望调用全量 XDR OpenAPI 能力 | 不阻塞真实告警输入；阻塞完整平台能力声明 | 补齐更多接口契约、错误码和联调样本 |
| XDR 日志查询接口未验收 | `xdr_log_query` 调用真实日志接口 | 不阻塞已命中告警进入审批；影响调查证据丰富度 | 索要日志接口路径、请求参数、返回结构和权限说明 |
| 真实高风险处置未接入 | 审批通过后期望真实封禁或隔离 | 阻塞生产处置动作 | 替换 Mock 工具并补审批、回滚、审计测试 |
| MySQL 模式未在本轮复验 | `STORAGE_BACKEND=mysql` 且连接真实数据库 | 不阻塞 memory 模式；影响持久化验收 | 准备数据库环境后补充回归 |
| Windows 启动未实机复验 | 当前任务执行机器为 macOS | 不影响 Linux/Docker 服务器部署；影响 Windows 环境声明 | 在 Windows 主机或 Windows runner 上执行 `python -m uvicorn sec_agent.main:app` 并访问 `/health` |

## 9. 验收结论

- 本轮可确认：当前后端可以通过现有 `POST /runs` 主链入口，从真实 XDR 告警列表接口拉取目标告警，并到达 `APPROVAL_REQUIRED`。
- 本轮可确认：Bridge 显式装配已落地，`Orchestrator` 可注入 Bridge，主链可消费注入 Bridge 的 `InvestigationReport` 并继续推进到审批。
- 本轮可确认：Bridge 对 `need_manual_takeover` 缺失/非法执行 fail-closed，并保留 `manual_takeover_reason` 与 `evidence_sources`。
- 本轮可确认：评测汇总入口框架已就绪，正式汇总文件可通过 `KNOWLEDGE_EVALUATION_SUMMARY_PATH` 接入同一套 Schema 守护测试。
- 本轮可确认：`GET /eval/comparisons` 已可用，返回 OFF/GUARDED 对比数据，并已进入 OpenAPI。
- 本轮可确认：评测对比接口已区分事件证据、工具查询结果和知识引用；已支持正式 JSON / 结果包目录 / `_summary.json` 读取、至少 6 案校验和 actual summary 自动生成。
- 本轮可确认：杨景凡正式 A/B 结果包已完成接口转换实测，20 行运行结果合并为 10 案 OFF/GUARDED 对比，case9 输出正式 `WSK-*` 命中知识 ID。
- 本轮可确认：服务器已部署 actual 结果包候选版本，公网 `/health` 与 `/eval/comparisons` 均通过；Docker 启动和 fixed_sample 固定样例回退通过。
- 本轮可确认：PR #49独有评测增量已基于`main@24fd76e`完成本地集成，主干正式门禁、域外报告、响应范围与评测接口可以共存。
- 本轮可确认：actual结果包脱敏元数据可正确输出运行Commit`0eb38cc`、代码基线、模型`deepseek-v4-flash`和工具模式；人工质量评分草案为GUARDED优胜3案、OFF优胜1案、同分6案，平均分5.8/8对5.7/8；知识门禁行为10/10符合预期，但不宣称通用准确率或显著提升。
- 本轮仍不能确认：逐案例耗时、可供接口加载的逐案胜负Review、XDR日志查询真实接口、真实高风险处置动作、MySQL真实环境持久化、FastGPT/远程Agent Bridge实现及最终服务器重部署结果。
- 是否影响上下游或主链：真实告警输入已可用；真实调查工具和生产处置能力仍需后续接入。
- 建议状态：已提交待验收。

## 10. 变更记录

| 日期 | 基线Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-26 | main / 5c05d61 | 新增主链测试记录文档，整理当前已执行回归、接口、CORS 和 OpenAPI 检查结果 | 阶段通过 |
| 2026-08-30 | 当前工作区 | 补充 XDR OpenAPI 告警接入单测、官方签名单测、真实告警输入联调记录和日志查询非阻断回归 | 阶段通过 |
| 2026-08-31 | 当前工作区 | 仅续跑真实 XDR `/runs` 主链输入，保存同一次运行的脱敏摘要、状态线和错误列表 | 阶段通过 |
| 2026-09-06 | 当前工作区 | 在主链三文档内补充 Bridge 与主链真实 Agent 接入装配设计 | 文档设计冻结 |
| 2026-09-06 | 当前工作区 | 落地 Bridge 显式装配并补主链级注入回归；未新增 fixture 或新文档文件 | 阶段通过 |
| 2026-09-06 | 当前工作区 | 补齐评测汇总正式入口框架，并记录默认 fixture 与显式路径入口复验结果 | 阶段通过 |
| 2026-09-07 | 当前工作区 | 新增 `GET /eval/comparisons` OFF/GUARDED 对比接口、OpenAPI 路径和 HTTP 回归 | 阶段通过 |
| 2026-09-09 | 当前工作区 | 完善 `GET /eval/comparisons`：新增证据分层字段、正式结果包读取、至少 6 案校验和 actual summary 生成回归 | 阶段通过 |
| 2026-09-11 | 当前工作区 | 根据 MCP/Agent/处置边界资料补齐 Bridge fail-closed、`evidence_sources` 保留、配置键和 OpenAPI 回归；后续已通过 SSH 密码登录完成服务器部署与健康检查 | 阶段通过 |
| 2026-09-14 | 当前工作区 | 将PR #49评测接口基于`main@24fd76e`重新集成；读取脱敏运行元数据；增加结构化人工Review入口；取消知识命中自动判优胜；保留主干门禁、域外报告和响应范围合同 | 本地集成通过，待远程CI |
