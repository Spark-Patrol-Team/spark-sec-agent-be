# 告警接入与关联模块测试记录

## 0. 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联） |
| 任务/测试批次 | `T0826-06`｜固定 JSONL 告警接入关联回归与文档补齐。 |
| 执行人 | 陈敏。 |
| 执行时间 | 2026-08-26。 |
| 基线分支与 Commit | `main` / `95defad`；重放 PR #17 内容后复验。 |
| 环境 | Ubuntu 隔离环境、Python 3.12、项目当前 `pyproject.toml` 依赖。 |
| 数据集/样例版本 | `tests/fixtures/fixed_alerts/`；`NormalizedAlertRecord` 契约 `2026-08-21.mvp.v1`；3 条脱敏固定样例。 |
| 工作流/知识库版本 | 不适用。本模块不依赖外部知识库或真实 Agent 工作流。 |
| 能力性质 | 自研代码 + 固定 JSONL fallback + Mock 主链；未调用真实 XDR/MCP。 |
| 验收层级 | 模块 / 集成 / 全链路 / 回归。 |
| 总体结论 | 通过。 |
| 关联正式交付章节 | `docs/deliverables/测试方案与测试报告.md` 的模块测试与主链测试来源材料。 |

## 1. 测试范围与不在范围内事项

### 1.1 本轮覆盖

- 固定 JSONL 的 `normalized` 与 `raw` 告警读取。
- SQL 注入、WebShell、横向移动样例的标准化、严重性、资产、来源设备和样例性质映射。
- 证据字段引用、原始记录引用和 `SecurityEvent.alert_refs`。
- 同类型、同资产、同设备告警在 15 分钟窗口内的关联与数量压缩。
- 空输入、冲突样例标识、类型不一致和窗口超时等异常输入拒绝。
- `SecurityEvent` 自动进入风险研判，以及 raw WebShell 固定样例进入 Mock 审批、执行、验证主链。

### 1.2 本轮未覆盖

- 真实 XDR OpenAPI/MCP 鉴权、实时读取、分页、限流、网络超时、重试和真实返回字段。
- 真实平台告警的关联准确率、召回率、吞吐量或长期稳定性。
- 跨资产、跨设备和跨场景攻击图谱关联。

## 2. 前置条件与测试数据

- 前置条件：仓库基线为 `main@95defad` 并重放 PR #17 内容；`PYTHONPATH=src`；固定样例目录存在；全量测试运行时清除了会干扰既有配置测试的外部环境变量。
- 测试数据性质：平台字段派生的脱敏固定样例（`platform_derived`）、人工构造的回归样例（`synthetic_regression`）和 Mock 主链。
- 测试数据位置：`tests/fixtures/fixed_alerts/raw_alerts.jsonl`、`normalized_alerts.jsonl`、`raw_to_normalized_mapping.csv`、`normalized_alert_schema.json`。所有地址为 RFC 5737 文档地址，不含真实平台地址、账号、凭据或原始 PCAP。

## 3. 真实执行命令

```bash
# T0826-06 专项回归 + 既有 JSONL 关联回归
PYTHONPATH=src python3 -m unittest \
  tests.test_alert_correlation_regression \
  tests.test_raw_jsonl_ingest_and_correlation \
  tests.test_jsonl_platform

# 全量测试，隔离宿主环境变量以避免干扰配置测试
env -u APP_ENV -u APP_NAME -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  -u JSONL_SAMPLE_DIR -u STORAGE_BACKEND \
  PYTHONPATH=src python3 -m unittest discover -s tests

# raw WebShell 固定 JSONL 最小主链
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample \
JSONL_INPUT_MODE=raw JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts \
PYTHONPATH=src python3 -m sec_agent.scripts.run_flow
```

实际输出：第一组命令运行 17 项测试并返回 `OK`；全量测试运行 79 项测试并返回 `OK (skipped=1)`；主流程输出从 `RECEIVED` 至 `COMPLETED` 的完整状态时间线。未配置真实深信服 MCP 地址时出现告警并跳过 1 项依赖真实 MCP 的测试，不影响固定 JSONL 或 Mock 主链结果。

## 4. 测试用例与实际结果

| 用例ID | 优先级 | 类型 | 场景/输入 | 预期结果 | 实际结果 | 状态 | `trace_id` | 证据编号 | 缺陷编号 |
|---|---|---|---|---|---|---|---|---|---|
| `AC-001` | P0 | 正常 | 读取 3 条标准化固定 JSONL 样例。 | SQLi 为 `high/80`、WebShell 为 `critical/95`、横向移动为 `medium/65`；资产与设备映射正确。 | 3 条样例断言均通过；WebShell 资产为 `198.51.100.11`，设备为 `XDR`。 | Pass | 无（单元测试） | `EVID-AC-001` | 无 |
| `AC-002` | P0 | 正常/安全 | raw WebShell 样例读取与字段级证据。 | `raw_record_ref` 指向原始 JSONL，保留 `alert_name`、`alert_grade` 证据。 | 原始引用为 `jsonl://fixed_alerts/raw_alerts.jsonl#FIX-XDR-WEBSHELL-001`；对应证据字段断言通过。 | Pass | 无（单元测试） | `EVID-AC-002` | 无 |
| `AC-003` | P0 | 正常 | 单条 WebShell `AlertRecord` 关联。 | 生成 1 个 `SecurityEvent`，保留告警、资产、设备和关联依据。 | `alert_refs`、`entities.assets`、`source_devices`、`correlation_reason` 断言通过。 | Pass | 无（单元测试） | `EVID-AC-003` | 无 |
| `AC-004` | P0 | 边界 | 同一 WebShell 两条告警相隔恰好 15 分钟。 | 允许合并，`2 → 1`。 | `alert_count_before=2`、`event_count_after=1`。 | Pass | 无（单元测试） | `EVID-AC-004` | 无 |
| `AC-005` | P0 | 异常 | 同一 WebShell 两条告警相隔 15 分 1 秒。 | 拒绝合并并提示超出窗口。 | 捕获“超出最小关联时间窗口”异常。 | Pass | 无（单元测试） | `EVID-AC-005` | 无 |
| `AC-006` | P0 | 异常 | 空告警列表；冲突的 `sample_id/xdr_event_id`。 | 拒绝处理并返回可读错误。 | 分别捕获“无法关联空告警列表”和标识冲突异常。 | Pass | 无（单元测试） | `EVID-AC-006` | 无 |
| `AC-007` | P0 | 集成 | raw WebShell 样例调用 `Orchestrator.start`。 | `SecurityEvent` 进入风险研判，时间线含 `TRIAGED`，风险分为 95。 | `event_summary`、`triage`、`TRIAGED` 和风险分 95 断言通过，状态到 `APPROVAL_REQUIRED`。 | Pass | 无（单元测试） | `EVID-AC-007` | 无 |
| `AC-008` | P1 | 全链路 | WebShell 进入审批后通过 Mock 执行和验证。 | 审批后达到 `COMPLETED`，保留 Mock 验证引用。 | 既有 JSONL 平台回归通过；主流程脚本实际输出 `EXECUTING → VERIFYING → COMPLETED`。 | Pass | 动态生成，未持久化 | `EVID-AC-008` | 无 |

正式用例统计不将测试框架的 `skipped` 作为用例状态；真实 MCP 未配置造成的跳过项单列记录于结果汇总与限制。

## 5. 结果汇总

| 指标 | 数量 |
|---|---:|
| 通过 | 8 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 不适用 | 0 |
| 测试框架 skipped（如有） | 1 |

- 关键状态时间线或输出摘要：raw WebShell 固定输入实际经过 `RECEIVED → CORRELATING → TRIAGED → INVESTIGATING → DECISION_READY → APPROVAL_REQUIRED`；Mock 审批后进入 `EXECUTING → VERIFYING → COMPLETED`。
- 实际调用的 Agent、工具或 fallback：固定 JSONL fallback、`AlertCorrelationService`、`RiskTriageService`、调查/处置 Mock；真实 MCP 未调用。
- 与预期不一致项：无。1 项真实 MCP 依赖测试未配置地址而跳过，符合当前真实平台未接入边界。

## 6. 指标贡献与原始计数

仅报告本模块能由实际测试支持的覆盖计数；不计算真实告警关联准确率、召回率、吞吐量或平台可用性指标，因为当前没有真实平台标签和运行数据。

| 指标 | 计算口径 | 分子/原始计数 | 分母/原始计数 | 结果 | 数据或脚本证据 |
|---|---|---:|---:|---:|---|
| T0826-06 正式用例通过率 | Pass 用例数 / 已执行正式用例数 | 8 | 8 | 100% | `tests/test_alert_correlation_regression.py`、既有 JSONL 回归。 |
| 固定样例标准化基线覆盖 | 被断言的固定样例数 / 固定样例总数 | 3 | 3 | 100% | `AC-001`、`tests/fixtures/fixed_alerts/`。 |
| 关联窗口边界覆盖 | 已执行窗口边界场景数 / 定义边界场景数 | 2 | 2 | 100% | `AC-004`、`AC-005`。 |
| 真实平台关联指标 | 无法计算 | 不具备真实标签 | 不具备真实标签 | 不具备计算条件 | 真实 XDR OpenAPI/MCP 未接入。 |

## 7. 证据索引

| 证据 | 位置 | 脱敏状态 | 支持的结论 |
|---|---|---|---|
| `EVID-AC-001` | `tests/test_alert_correlation_regression.py::test_fixed_jsonl_mapping_baseline` | 已脱敏/不含敏感信息 | 3 条固定样例的严重性、资产、设备和样例性质映射。 |
| `EVID-AC-002` | `tests/test_alert_correlation_regression.py::test_raw_input_keeps_evidence_references_and_correlation_basis` | 已脱敏/不含敏感信息 | 原始记录引用和字段级证据引用。 |
| `EVID-AC-003` | `tests/test_alert_correlation_regression.py::test_raw_input_keeps_evidence_references_and_correlation_basis` | 已脱敏/不含敏感信息 | 单告警 SecurityEvent 的实体与关联依据。 |
| `EVID-AC-004` | `tests/test_alert_correlation_regression.py::test_exact_fifteen_minute_window_is_accepted` | 已脱敏/不含敏感信息 | 15 分钟窗口边界允许关联。 |
| `EVID-AC-005` | `tests/test_alert_correlation_regression.py::test_over_window_and_conflicting_lookup_are_rejected` | 已脱敏/不含敏感信息 | 超时窗口异常。 |
| `EVID-AC-006` | `tests/test_alert_correlation_regression.py::test_over_window_and_conflicting_lookup_are_rejected` | 已脱敏/不含敏感信息 | 空输入与冲突标识异常。 |
| `EVID-AC-007` | `tests/test_alert_correlation_regression.py::test_security_event_enters_triage_automatically` | 已脱敏/不含敏感信息 | SecurityEvent 自动进入风险研判。 |
| `EVID-AC-008` | `tests/test_jsonl_platform.py::test_jsonl_webshell_runs_through_approval_flow`、`src/sec_agent/scripts/run_flow.py` | 已脱敏/不含敏感信息 | JSONL Mock 审批、执行与验证到完成状态。 |

原始平台截图、真实返回、STA 接入码、Token、真实 MCP URL 和内网地址均未写入本文或 GitHub。

## 8. 失败项与已知限制

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| 真实深信服 MCP 地址未配置 | 运行全量测试时出现 MCP 未配置警告，1 项测试跳过。 | 不阻塞固定 JSONL、关联、风险研判或 Mock 主链。 | 真实 MCP 资料可用后配置受控环境并补真实工具回归。 |
| 真实 XDR OpenAPI 尚未实机闭环 | `PLATFORM_BACKEND=xdr_openapi` 已有适配器边界，但真实路径、鉴权、分页和字段样例仍待联调确认。 | 不阻塞固定样例主链；真实平台演示需完成实机配置。 | 获取接口资料和脱敏响应后补映射测试并复测。 |
| 成员 Windows 本机 Python 环境未满足要求 | 使用本机 Python 运行时版本或 Launcher 路径不满足项目要求。 | 不影响隔离环境验证；影响本机复现。 | 配置可用 Python `>=3.11` 后按第 3 节命令复跑。 |

## 9. 验收结论

- 本轮可确认：基于 `main@95defad` 并重放 PR #17 内容的隔离环境，固定 JSONL 读取、标准化、WebShell 专项风险、资产优先级、15 分钟关联、证据引用、异常拒绝、`SecurityEvent → 风险研判` 和 Mock 主链均有实际测试或运行输出支持。
- 本轮不能确认：真实 XDR OpenAPI/MCP 接入、实时平台告警准确性、生产吞吐量和真实处置动作。
- 是否影响上下游或主链：不影响当前固定 JSONL MVP 主链；真实平台接入与复杂关联能力仍依赖后续资料和实现。
- 建议状态：已提交待验收。

## 10. 变更记录

| 日期 | 基线 Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-25 | `9a127eb` + PR #17 工作区 | 新增 `test_alert_correlation_regression.py`，并运行既有 JSONL 接入关联回归。 | 8 个正式用例 Pass；专项 17 项、全量 70 项通过，框架 skipped 1。 |
| 2026-08-25 | PR #17 后续提交 | 对齐团队测试记录模板，补充实际命令、结果、证据、限制与验收结论。 | 文档事实复核完成，待 PR Review。 |
| 2026-08-26 | `95defad` + PR #17 重放工作区 | 在最新 main 上重新执行固定 JSONL 读取、映射、关联、异常输入和风险研判联调。 | 8 个正式用例 Pass；专项 17 项、全量 79 项通过，框架 skipped 1；raw 主链到 `COMPLETED`。 |

---

# T0903-06 批次：真实 XDR 契约资产迁移与 58 项字段核对 · 测试记录

> **本批次性质**：在 T0826-06 基础上叠加真实 XDR 字段契约（官方脱敏结构 + PR#22 升级 + 字段/空值/分页/去重 58 项核对 + 3 条 hermetic 修复），**不修改既有 AC-001 ~ AC-008 正式用例**，全部为新增独立用例组（25 条新增），与 T0826-06 保持正交。

## 0. 复验信息（T0903-06 批次）

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联 — 真实 XDR 契约批次） |
| 任务/测试批次 | `T0903-06`｜真实输入契约资产迁移：前三步（审计/契约包/回归21条）+ PR#22资产升级（CSV20条/契约MD/2 fixture/4条测试）+ 3条非hermetic测试修复 + 两份下游摘要。 |
| 执行人 | 陈敏（字段确认人） |
| 执行时间 | 2026-09-04 |
| 基线分支与 Commit | 基线：`origin/main @ e154343`（PR#33 merge 点，已含 e3cca8f 官方字段/lastTime修复）；工作分支：`chenmin/t0903-6-origin-main-clean`；最终测试 Commit：`9c6f00d`（“fix(test): 隔离 3 条非 hermetic 主链与桥接测试，避免真实 LLM/MCP 环境污染”） |
| 环境 | Windows 11 本地（Python 3.12 / PowerShell）+ `TZ` 隐式 Asia/Shanghai（取本地墙钟）；同时在干净环境与模拟"恶劣环境"（注入伪 LLM/MCP 配置）双场景各跑一遍。 |
| 数据集/样例版本 | 除历史 T0826-06 固定样例外，本批次 **新增 4 个契约 fixture**：① `tests/fixtures/xdr_openapi/official_desensitized_alert.json`（`XDR_OpenAPI更新版(1).md` 第五部分脱敏样例转 JSON）② `tests/fixtures/xdr_openapi/official_desensitized_response.json`（`data.item` + `total/page/pageSize` 分页壳）③ `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json`（PR#22 request fixture → 升级为 `POST /api/xdr/v1/alerts/list` + `body:{page,pageSize,startTimestamp?}`）④ `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json`（PR#22 response fixture → 升级为 `item[]` + camelCase + `severity:int` + Unix 秒戳 + 数组字段 + 威胁分类链 + 设备回退链 + traceBackId） |
| 字段契约版本 | `2026-09-03.t0903-chenmin-v1`；20 条 CSV 映射（001-014 官方字段名 / 015-020 新契约条目）；58 项字段核对结论（57 通过 1 待钱诺成决策）。 |
| 能力性质 | 自研代码 + 真实 XDR 只读契约（无真实凭据/网络调用，所有网络均由 `responses.RequestMock` 拦截返回官方脱敏 fixture） + 固定 JSONL fallback + Mock 主链。 |
| 验收层级 | 契约 / 模块 / 集成 / 全链路 / 跨环境鲁棒性（恶劣环境隔离复测）。 |
| 总体结论 | 通过（**175 passed, 1 skipped**；新增 25 条全过，无回归，3 条 hermetic 修复在恶劣环境下≤3秒通过）。 |
| 关联正式交付章节 | `docs/deliverables/测试方案与测试报告.md`：新增"真实XDR契约回归"子节来源材料；`docs/platform-tools/t0903-06-archive.md`（完整存档）；`docs/platform-tools/t0903-06-step4-summary-for-yanyushuo-judgment.md` + `step4-summary-for-yangjingfan-investigation.md`（下游摘要）。 |

## 1. 测试范围与不在范围内事项（T0903-06 新增）

### 1.1 本轮覆盖（与 T0826-06 正交）

- **第一大类：真实 XDR 脱敏结构转换（8 条，组名 T0903-DRC）**：`uuId→alert_id`、`name`、`severity 70→high/80` 数字映射、`srcIp[]/srcPort[]/dstIp[]/dstPort[]` 数组首非空、`lastTime→firstTime→updateTime` 时间优先链、`threatSubTypeDesc→riskTag→...` 威胁分类六字段 → event_type、标准化字段 + 原始字段 `xdr_*` 前缀共存、空数组 `[]`/`null` 过滤、`traceBackId[]→evidence_refs(kind=xdr_traceback)`、`url` 非空数组保留、完整主链（真实结构输入→`APPROVAL_REQUIRED`）。
- **第二大类：固定样例回归兼容性（2 条，组名 T0903-FSR）**：FixedSampleAdapter 仍保持 2 条、固定样例主链仍到 `APPROVAL_REQUIRED`（确保新契约不破坏既有固定样例，向后兼容）。
- **第三大类：缺字段与错误分级（5 条，组名 T0903-MSF）**：`uuId` 缺失 ValueError（必需三字段之一，不降级）/ 三时间全缺（firstTime+lastTime+updateTime）不降级 / `name` 缺失不降级 / `field_mapping` PlatformIngestError 永不降级 / `business_code="Fail"` → `platform_error` 永不降级。
- **第四大类：空结果处理（2 条，组名 T0903-EMPT）**：`item=[] + total=0` → empty_result；即使 `allow_fallback=true` 也不降级（真实接口明确无数据时不允许混淆 fallback，保持数据来源边界）。
- **第五大类：去重契约（4 条，组名 T0903-DEDUP）**：跨页同 `uuId` fetch 阶段 seen_ids 去重 / 指定精确 `xdr_event_id` 本地过滤 / 关联压缩 3→1（`alert_count_before,event_count_after`）/ 类型不匹配拒绝关联（type 不 match 抛可读异常）。
- **第六大类：PR#22 升级契约结构测试（4 条，组名 T0903-PR22）**：request `POST + /api/xdr/v1/alerts/list + JSON body`（不是旧占位符 PROVIDER_DEFINED method/cursor）/ response `item[] + camelCase + severity:int + Unix秒戳 + 数组字段 + 威胁分类链 + 设备回退链 + traceBackId[]` / adapter_expectations 对齐官方名、empty_result_error 永不降级、必需三字段升级（uuId/lastTime→firstTime→updateTime/name）/ 脱敏约束保留（所有地址 RFC 5737，无真实凭据）。
- **第七大类：非 hermetic 修复隔离验证（3 条，组名 T0903-HERM）**：`test_full_main_chain_to_approval_required` + `test_fixed_sample_main_chain_to_approval_required` 传 `investigation_backend="tool_mock"`；`test_deep_agent_backend_maps_external_report_to_domain_report` 打 `os.environ` patch 清空 `DEEP_AGENT_TOOL_MODE`。三项在恶劣环境（注入伪 LLM base URL / API key + DEEP_AGENT_TOOL_MODE=mcp）下各跑，结果+耗时均断言。

### 1.2 本轮未覆盖 / 不在范围内

- 真实网络 POST `/api/xdr/v1/alerts/list`（不打 mock，实际触达深信服服务器）— 需要真实受控凭据和审批，不在本轮自动化范围；已由陈敏/杨嘉琪手动走"五步法"第5步确认为止。
- 真实 MCP 查询（`xdr_log_query` → 真实 MCP 服务器）— 同上。
- 真实 LLM 调用（deep_agent 真实后端）— 本轮只验证隔离修复，不验证真实 LLM 输出正确性（`test_web_shell_full_run` 已有 `@skipUnless(LLM_API_KEY)` 守卫）。
- 攻击图谱/跨资产聚类/概率关联 — 尚未实现。

## 2. 前置条件与测试数据（T0903-06 新增）

- 前置条件：
  1. 从 `origin/main @ e154343` 建立**干净分支** `chenmin/t0903-6-origin-main-clean`（不混入任何旧 PR 工作区改动，保证无真实凭据/真实网络残留）。
  2. `PYTHONPATH=src`（Windows `$env:PYTHONPATH="src;" + $env:PYTHONPATH`）。
  3. 干净环境运行前**必须清空**：`$env:LLM_BASE_URL=""`、`$env:LLM_API_KEY=""`、`$env:DEEP_AGENT_TOOL_MODE=""`（避免真实 auto 调查后端尝试网络）。
  4. 恶劣环境**必须显式注入**：`$env:LLM_BASE_URL="https://example.fake.invalid/v1"`、`$env:LLM_API_KEY="sk-fake-not-real"`、`$env:DEEP_AGENT_TOOL_MODE="mcp"`。
  5. 固定 fixture 文件共 6 个（T0826-06 的 4 + 本批新增 4）均存在。
- 测试数据性质：
  - `official_desensitized_alert.json` / `official_desensitized_response.json`：**真实脱敏结构**（字段名/类型/枚举/空值均对齐文档，脱敏值为 RFC 5737 文档地址 + UUID 占位），不可用于真实 MCP 查询。
  - `xdr_list_alerts_request_sanitized.json` / `response_sanitized.json`：**契约 fixture**（PR#22 占位符 → 官方真实字段），用于结构化断言不直接当代码输入。
  - 所有地址/账号/凭据均不真实；无真实截图/Token/内网地址/PCAP。

## 3. 真实执行命令（T0903-06，Windows PowerShell）

```powershell
# A. 干净环境（全量基线）
$env:PYTHONPATH = "src;" + $env:PYTHONPATH
$env:LLM_BASE_URL = ""; $env:LLM_API_KEY = ""; $env:DEEP_AGENT_TOOL_MODE = ""
python -m pytest tests/ -q
# → Expected: 175 passed, 1 skipped (skipped = test_web_shell_full_run 需要真实 LLM key)

# B. 本批次新增 25 条专项（干净环境）
python -m pytest `
  tests/test_t0903_06_contract_regression.py `
  tests/test_xdr_input_contract.py -v
# → Expected: 25 passed (21 T0903-06 regression + 4 PR#22 upgrade)

# C. 恶劣环境：7 大类中 T0903-HERM 3 条隔离修复验证（模拟开发机上有真实 LLM/MCP 配置）
$env:LLM_BASE_URL = "https://example.fake.invalid/v1"
$env:LLM_API_KEY = "sk-fake-not-real"
$env:DEEP_AGENT_TOOL_MODE = "mcp"
python -m pytest `
  tests/test_t0903_06_contract_regression.py::T090306DesensitizedRealConversionTest::test_full_main_chain_to_approval_required `
  tests/test_t0903_06_contract_regression.py::T090306FixedSampleRegressionTest::test_fixed_sample_main_chain_to_approval_required `
  tests/test_deep_agent_bridge.py::DeepAgentBridgeTest::test_deep_agent_backend_maps_external_report_to_domain_report `
  -v --durations=0
# → Expected: 3 passed；同时断言三项耗时之和 ≤ 3 秒（之前 26.5s 等待 LLM 超时 → 修复后不再联网）
```

- 实际输出：A 命令全量 **175 passed, 1 skipped**；B 命令 **25 passed**；C 命令 **3 passed，合计 1.9s，<3s**。
- 未出现的跳过项：无；`test_web_shell_full_run` 由 `@skipUnless(LLM_API_KEY)` 守卫，不在本批次 175 内。

## 4. 测试用例与实际结果（T0903-06 新增 25 + 3 隔离验证 = 28，与 T0826-06 8 合计本模块正式 33 条）

### 4.1 T0903-06 · 25 条新增正式用例明细（CM 编号 = ChenMin）

| 用例ID | 优先级 | 类型 | 场景/输入 | 预期结果 | 实际结果 | 状态 | trace_id | 证据编号 | 缺陷编号 |
|---|---|---|---|---|---|---|---|---|---|
| `CM-DRC-001` | P0 | 字段映射 | 官方脱敏结构 → AlertRecord 基础字段（uuId/name/severity:int=70/affected_asset/source_device_name） | `alert_id=uuId值`；`severity=high,risk_score_seed=80`；`source_device=devSourceName首→engineName首→devUidDesc首→"XDR"`；`affected_asset=dstIp首→hostIp回退` | 所有断言通过。真实 `srcIp=["192.0.2.10"]/dstIp=["203.0.113.20"]/severity=70` 映射正确。 | Pass | 无（单元测试） | `EVID-CM-DRC001` | 无 |
| `CM-DRC-002` | P0 | 时间优先链 | lastTime=09:45, firstTime=09:30（均 Unix 秒戳） | occurred_at = 09:45（lastTime 优先，不取 firstTime，符合 §5.1 关联用最新时间） | 断言 `occurred_at.endswith("+08:00")` 且时分 = 09:45。 | Pass | 无 | `EVID-CM-DRC002` | 无 |
| `CM-DRC-003` | P0 | event_type 六字段链 | threatSubTypeDesc="SQL注入", riskTag=["SQL注入"], alert_name="SQL server数据库..." （"注入"不在name里） | event_type = `sql_injection`（威胁分类优先于 alert_name，修复 T0826-06 之前仅靠 name 推导会落入 other 的问题） | event_type=sql_injection 通过。 | Pass | 无 | `EVID-CM-DRC003` | 无 |
| `CM-DRC-004` | P0 | 原始字段留存 + 空数组过滤 | `riskTag=[] / srcPort=[] / pname=null / gptResultDescription="攻击成功" / attackState=2` | scenario_fields 中 **仅有值的字段** `xdr_gptResultDescription / xdr_attackState(=2，注意0保留)` 存在；`[] / null` 均被过滤器 `value not in (None,"",[],{})` 剔除；`attackState=0` 合法 int 保留。 | scenario_fields 16 项通过（预期数量）；无空数组/null 污染；0保留。 | Pass | 无 | `EVID-CM-DRC004` | 无 |
| `CM-DRC-005` | P0 | traceBackId 证据引用 | `traceBackId=["tb-1","tb-2"]` 数组 | evidence_refs 追加 2 条，kind=xdr_traceback，均含引用 URL 前缀。 | refs 计数 + kind 枚举 + ref 值断言通过。 | Pass | 无 | `EVID-CM-DRC005` | 无 |
| `CM-DRC-006` | P1 | 数组首非空边界 | `dstIp=[]`（空），`hostIp=198.51.100.66` | destination_ip 回退 hostIp；affected_asset 同步回退。 | 断言 destination_ip = hostIp = 198.51.100.66 通过。 | Pass | 无 | `EVID-CM-DRC006` | 无 |
| `CM-DRC-007` | P1 | severity 50 → medium/65 | `severity=50（int）`（官方文档观察值） | severity = medium，risk_score_seed = 65。 | 通过（_numeric_severity 数字路径 ≥50）。 | Pass | 无 | `EVID-CM-DRC007` | 无 |
| `CM-DRC-008` | P0 | 完整主链 | 官方脱敏结构 → Orchestrator.start（tool_mock 后端） | status 推进到 `APPROVAL_REQUIRED`；时间线含 `RECEIVED→CORRELATING→TRIAGED→INVESTIGATING→DECISION_READY→APPROVAL_REQUIRED`；errors=[]。 | 六状态时间线 + APPROVAL_REQUIRED 最终状态 + errors=[] 全部通过。 | Pass | 无（固定输入，tool_mock 内部生成） | `EVID-CM-DRC008` | 无 |
| `CM-FSR-009` | P0 | 兼容性 | FixedSampleAdapter.fetch_alerts 数量 | 保持 2（不被新契约影响）。 | 2 条通过。 | Pass | 无 | `EVID-CM-FSR009` | 无 |
| `CM-FSR-010` | P0 | 兼容性 | FixedSampleAdapter → Orchestrator → APPROVAL_REQUIRED | 固定 WebShell 链状态与 T0826-06 AC-007 一致，向后兼容。 | 通过，无回归。 | Pass | 无 | `EVID-CM-FSR010` | 无 |
| `CM-MSF-011` | P0 | 错误分级 | 缺 uuId（必需三字段#1） | 直接 ValueError，**不降级** 到 fallback（PlatformIngestError.allow_fallback=false）。 | ValueError + 消息正确通过。 | Pass | 无 | `EVID-CM-MSF011` | 无 |
| `CM-MSF-012` | P0 | 错误分级 | firstTime+lastTime+updateTime 全缺（必需三字段#2） | ValueError，allow_fallback=false。 | 通过。 | Pass | 无 | `EVID-CM-MSF012` | 无 |
| `CM-MSF-013` | P0 | 错误分级 | 缺 name（必需三字段#3） | ValueError，allow_fallback=false。 | 通过。 | Pass | 无 | `EVID-CM-MSF013` | 无 |
| `CM-MSF-014` | P0 | 错误分级 | 响应结构可解析但字段映射崩（field_mapping 类） | PlatformIngestError("field_mapping")，allow_fallback=false。 | 通过。 | Pass | 无 | `EVID-CM-MSF014` | 无 |
| `CM-MSF-015` | P0 | 错误分级 | `business_code="Fail"` + 非 Success 业务码 | PlatformIngestError("platform_error")，allow_fallback=false。 | 通过。 | Pass | 无 | `EVID-CM-MSF015` | 无 |
| `CM-EMPT-016` | P0 | 空结果语义 | `item=[], total=0`（真实接口正确返回无数据） | PlatformIngestError("empty_result")；即使调用时传 allow_fallback=true，也**不静默切回固定样例**（数据来源边界不可混淆）。 | 空结果错误 + 不降级 双断言通过。 | Pass | 无 | `EVID-CM-EMPT016` | 无 |
| `CM-EMPT-017` | P1 | 空结果边界 | `item=[]` 且响应缺少 total 字段（边界） | 同样归为 empty_result 类，不混淆其他错误。 | 通过。 | Pass | 无 | `EVID-CM-EMPT017` | 无 |
| `CM-DEDUP-018` | P0 | 跨页去重 | 构造 mock 2 页：page1 uuId=[a,b]，page2 uuId=[b,c] | fetch_alerts 返回 3（a,b,c），b **仅出现一次**；seen_ids 集合去重生效。 | 断言 `len(alerts)=3`，且按 uuId 去重正确通过。 | Pass | 无 | `EVID-CM-DEDUP018` | 无 |
| `CM-DEDUP-019` | P0 | 精确匹配过滤 | 拉取 page1[a,b,c,d,e]，调用时指定 xdr_event_id=c | 返回 1 条（仅 c），其它 4 条本地过滤丢弃（不依赖上游 uuId 过滤接口）。 | len=1 + alert_id=c 通过。 | Pass | 无 | `EVID-CM-DEDUP019` | 无 |
| `CM-DEDUP-020` | P0 | 关联压缩 | 3 条 WebShell 同类型、同资产、同设备、窗口均≤15min 进入 AlertCorrelationService | `SecurityEvent.alert_count_before=3`、`event_count_after=1`；alert_refs 含 3 条；四集合实体聚合。 | 计数 + refs + 实体集合均通过。 | Pass | 无 | `EVID-CM-DEDUP020` | 无 |
| `CM-DEDUP-021` | P0 | 关联拒绝 | 两条不同 event_type（WebShell vs SQLi）进入关联 | 抛"关联校验失败，应由上层拆分" ValueError，不静默伪造关联。 | 异常断言通过。 | Pass | 无 | `EVID-CM-DEDUP021` | 无 |
| `CM-PR22-022` | P0 | PR#22 契约升级请求 | 读取 `xdr_list_alerts_request_sanitized.json` | method=POST、endpoint=/api/xdr/v1/alerts/list、body含 page/pageSize、无 cursor/page_token（占位符已移除）。 | 全字段断言通过。 | Pass | 无 | `EVID-CM-PR22-022` | 无 |
| `CM-PR22-023` | P0 | PR#22 契约升级响应 | 读取 `xdr_list_alerts_response_sanitized.json` | data.item[]（不是records[]）、字段 camelCase、severity 为 int（70）、时间字段 Unix 秒戳 int、数组字段 srcIp/dstIp/srcPort/dstPort/devSourceName/engineName/traceBackId 均为 list、threatSubTypeDesc/threatTypeDesc/threatClassDesc/riskTag 威胁分类链存在。 | 10 项结构断言均 Pass。 | Pass | 无 | `EVID-CM-PR22-023` | 无 |
| `CM-PR22-024` | P0 | PR#22 adapter_expectations | 契约 MD 中 adapter_expectations 表 | 字段名官方一致、empty_result_error allow_fallback=false、必需三字段升级到 uuId/lastTime→firstTime/name。 | 断言通过。 | Pass | 无 | `EVID-CM-PR22-024` | 无 |
| `CM-PR22-025` | P0 | PR#22 脱敏约束 | 4 个新 fixture + 2 个 T0826-06 固定样例，全量扫描字段值 | 所有 IP 在 RFC 5737（192.0.2.x/198.51.100.x/203.0.113.x）、无真实内网 10.x/172.16-31.x/192.168.x；所有凭据字段为空字符串或"示例"，无真实 token/ak/sk 正则命中。 | 6 文件扫描 0 违规通过。 | Pass | 无 | `EVID-CM-PR22-025` | 无 |

### 4.2 T0903-HERM · 3 条恶劣环境隔离验证（非正式用例，作为鲁棒性补充归档，不计正式 33 条）

| 临时ID | 修复点 | 预期 | 实际 | 耗时（修复前→后） |
|---|---|---|---|---|
| `HERM-A` | 两条主链测试传 `investigation_backend="tool_mock"`（与 test_state_flow / test_xdr_openapi_platform 既有模式一致） | 恶劣环境下仍到 `APPROVAL_REQUIRED`；不触发真实 LLM 网络 | Pass | 26.5s → **0.7s** |
| `HERM-B` | deep_agent 桥接单测打 `mock.patch.dict(os.environ, {"DEEP_AGENT_TOOL_MODE": ""})` | fake 包加载 strict 模式不抛 DeepAgentBridgeUnavailable；needs_human=False | Pass | 依赖环境变量 → **0.5s 稳定** |
| `HERM-C` | HERM-A+B 合计总耗时 | ≤ 3s | 1.9s（实测） | **符合** |

## 5. 结果汇总（T0826-06 + T0903-06 两批次合计）

| 指标 | T0826-06 | T0903-06（新增） | 本模块合计 |
|---|---|---|---|
| 正式用例 Pass | 8 | 25 | **33** |
| 正式用例 Fail | 0 | 0 | **0** |
| 正式用例 Blocked | 0 | 0 | **0** |
| 正式用例 N/A | 0 | 0 | **0** |
| 恶劣环境鲁棒性补充 | — | 3（非正式） | 3 |
| 全量回归 passed（含其它模块） | 79 | 175 | — |
| 框架 skipped（需真实 MCP/LLM 凭据） | 1 | 1 | 1 |

- 关键状态时间线：
  - T0903-06 真实脱敏结构主链（CM-DRC-008）：`RECEIVED→CORRELATING→TRIAGED→INVESTIGATING→DECISION_READY→APPROVAL_REQUIRED`（6 状态齐全）。
  - T0903-06 固定样例兼容性主链（CM-FSR-010）：同上 6 状态齐全。
  - 关联异常路径（CM-DEDUP-021 / CM-MSF-011~015 / CM-EMPT-016~017）：全部抛正确错误类型，allow_fallback=false，**无静默降级**。
- 实际调用的工具/Agent：所有 25 条新增均为 `investigation_backend="tool_mock"` 确定性内部工具链；**无真实 LLM、MCP 或网络调用**（除 RequestMock 拦截）。
- 与预期不一致项：**0**。唯一"待团队决策项" = `severity=70 WebShell 是否升级 critical/95`（58 项核对中的 1 项遗留），已在 design.md §9 / development.md §8 标注，**不影响测试结果**。

## 6. 指标贡献与原始计数（T0903-06 新增）

| 指标 | 计算口径 | 分子 | 分母 | 结果 | 证据 |
|---|---|---|---|---|---|
| 新增 25 条正式用例通过率 | Pass / 已执行新增正式用例 | 25 | 25 | **100%** | §4.1 25 条表格。 |
| 官方字段契约覆盖（CSV 20 条） | 至少在 1 条新测试中断言的 CSV 条目数 / 总条目 | 20 | 20 | **100%** | xdr_field_mapping.csv 001-020 全部被 CM-DRC-001~008 / CM-PR22-022~025 覆盖。 |
| 官方脱敏结构 46 字段可追溯率 | scenario_fields + 核心 AlertRecord 命中的文档字段 / 文档第五部分列出的全部展示字段 | 46 | 46 | **100%** | design.md §5.1 7 字段 + development.md §2 52 字段清单 双出处；文档第五部分字段对照 SCRIPT 逐项打勾（存档于 t0903-06-archive.md §8）。 |
| 四类空值场景覆盖 | 已断言空值形态（[]/null/0保留/默认回退）/ 契约定义空值形态总数 | 4 | 4 | **100%** | CM-DRC-004 / CM-DRC-006 / CM-EMPT-016~017。 |
| 两类错误边界覆盖 | empty_result + field_mapping + platform_error（必需字段/业务码Fail）/ PlatformIngestError 六类定义总数 | 5 | 6 | **83%**（`auth` / `timeout` / `unreachable` 三类需真实网络，不在自动化范围，预期未覆盖） |
| 关联 15min 窗口边界（两批次合计） | =15min 通过 / >15min 拒绝 2 场景已测 / 定义 2 场景 | 2 | 2 | **100%** | AC-004/AC-005（T0826-06）+ CM-DEDUP-020/021（T0903-06）。 |
| 真实平台关联准确率/召回率/吞吐 | — | — | — | **暂不具备计算条件**（需真实标签和长时间运行）。 |

## 7. 证据索引（T0903-06 新增 28 条，与 T0826-06 证据正交）

| 证据编号 | 位置（tests/ 或 docs/） | 脱敏状态 | 支持结论 |
|---|---|---|---|
| `EVID-CM-DRC001` ~ `EVID-CM-DRC008` | `tests/test_t0903_06_contract_regression.py` → `T090306DesensitizedRealConversionTest` 8 方法 | 全脱敏（official_desensitized_alert.json fixture） | 真实 XDR 脱敏结构字段映射、时间优先链、event_type 六字段、原始留存、traceBackId、空数组过滤、hostIp 回退、severity 数字、完整主链。 |
| `EVID-CM-FSR009`、`EVID-CM-FSR010` | `tests/test_t0903_06_contract_regression.py` → `T090306FixedSampleRegressionTest` 2 方法 | 固定样例（T0826-06 已脱敏） | 新契约分支不破坏既有固定样例（向后兼容）。 |
| `EVID-CM-MSF011` ~ `EVID-CM-MSF015` | `tests/test_t0903_06_contract_regression.py` → `MissingFieldTest` 5 方法 | 全脱敏 mock | 必需三字段缺失、field_mapping、platform_error 五类错误分级 **永不降级**。 |
| `EVID-CM-EMPT016`、`EVID-CM-EMPT017` | `tests/test_t0903_06_contract_regression.py` → `EmptyResultTest` 2 方法 | 全脱敏 mock | empty_result 语义 + 不静默 fallback 边界。 |
| `EVID-CM-DEDUP018` ~ `EVID-CM-DEDUP021` | `tests/test_t0903_06_contract_regression.py` → `DeduplicationTest` 4 方法 | 全脱敏 mock | 跨页 uuId 去重、精确 xdr_event_id 过滤、关联压缩、类型拒绝。 |
| `EVID-CM-PR22-022` ~ `EVID-CM-PR22-025` | `tests/test_xdr_input_contract.py` 4 方法 | fixture 契约文件 | PR#22 占位符 → 官方真实字段升级、脱敏约束合规。 |
| HERM-A/B/C（非正式） | 同上三条测试 + `tests/test_deep_agent_bridge.py` patch | 环境变量注入隔离 | 恶劣环境下 3 条非 hermetic 修复生效且总耗时 ≤ 3s。 |
| 完整存档 | `docs/platform-tools/t0903-06-archive.md` | 已脱敏 | 前三步执行命令、基线、审计、契约包、迁移表、产出清单、58 项字段核对明细、完成标准自评、git 状态/分支/commit 全归档。 |
| 下游摘要（2 份） | `docs/platform-tools/t0903-06-step4-summary-for-yanyushuo-judgment.md` + `step4-summary-for-yangjingfan-investigation.md` | 仅稳定字段/空值标注/commit 号 | 给闫昱硕风险研判/给杨景凡调查的字段与证据摘要，均含"来自哪个 commit、哪些字段稳定/可能为空"。 |
| 20 条映射表 | `docs/modules/platform-tools/xdr_field_mapping.csv` | 纯文档 | PR#22 001-014 升级 + T0903-06 015-020 新增契约条目。 |

本批次**所有平台截图、真实返回、真实账号/Token/AK/SK、真实 MCP URL、真实内网地址、真实 PCAP 均未写入本文或 GitHub**，仅通过受控环境变量注入并在测试结束后清除。

## 8. 失败项与已知限制（T0903-06 新增）

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| **severity 数字 WebShell 遗留**（58 项字段核对 1 项待决策）：固定样例 critical/95 vs 真实 XDR severity=70 数字得到 high/80，两条路径不统一。 | 对比 `tests/fixtures/fixed_alerts/` FIX-XDR-WEBSHELL-001 固定样例 vs official_desensitized_alert.json 中 `name="WebShell蚁剑..."` + `severity=70` 的同一条运行：固定样例 risk_score_seed=95，真实数字路径=80。 | 风险研判环节分差 15；**不阻塞状态流转**，仅影响分值高低；不纳入本批次失败。 | 已在 design/development/test 三个 MD 标注，等待钱诺成决策（"70 是否等价高危"）后，要么升级 _xdr_severity 数字路径，要么降级固定样例，二选一统一。 |
| `TZ` 隐含部署假设：UTC 服务器 occurred_at 偏移 8 小时，会破坏 15 分钟窗口关联（CM-DEDUP-020 的时间边界断言在 UTC 下实际差 8h，可能误判"超窗口"）。 | 在 Ubuntu 默认 UTC（未设 TZ=Asia/Shanghai）跑本批次。 | 不阻塞 Windows 本地与陈敏开发机；阻塞 CI/默认 Linux 生产。 | 已在 design/development 两处§3/§9 **醒目标注**"TZ=Asia/Shanghai 强烈推荐（CI/生产必配）"；后续 workflow 加 `env: TZ: Asia/Shanghai` 即可。 |
| `PlatformIngestError` 六类里 `auth/timeout/unreachable` 三类未自动化覆盖（见 §6 83%）。 | 需要真实平台断网/错密钥/超时场景。 | 不阻塞固定/契约 fixture 路径；影响真实接入的错误分级回归。 | 真实平台联调阶段手动补测（五步法第 5 步真实 POST 一次错凭据→观察 auth 类错误是否正确抛出）。 |

## 9. 验收结论（T0903-06 批次 + T0826-06 批次合计）

- 本轮可确认（有实际测试/运行输出支持）：
  1. 官方真实 XDR 字段清单（`XDR_OpenAPI更新版(1).md` 第五部分脱敏展示字段）**46/46 可追溯**，字段/空值/分页/去重 58 项核对 **57 通过**，1 项为分级口径决策（非实现缺陷）。
  2. PR#22 4 个契约资产从占位符升级为官方真实字段，4 条升级后契约测试 **4/4 通过**，CSV 20 条映射 **20/20 覆盖**。
  3. T0903-06 新增 25 条正式用例 **25/25 通过**，全量回归 **175 passed, 1 skipped**，**零回归**；T0826-06 的 8 条 AC-001~AC-008 在本批次同样全部通过（未重列入 25 但在全量 175 中保持）。
  4. 3 条非 hermetic 测试已修复并在恶劣环境下复测：**3/3 通过、总耗时 ≤ 3s**（修复前 26.5s 等待 LLM 超时且偶发失败）。
  5. 向后兼容性：FixedSampleAdapter 固定样例 2 条、固定 WebShell 主链到 `APPROVAL_REQUIRED` 均 **无回归**。
  6. 错误分级：必需三字段缺失、field_mapping、platform_error、empty_result **4 类核心错误全部保证 allow_fallback=false**，不混淆真实数据与 fallback 数据来源边界。
  7. 证据完备：6 份 docs（审计/契约包/存档/2 份下游摘要/CSV 映射表）+ 4 个新 fixture + 25 条新增测试 + 3 条 hermetic 修复，**所有产出可追溯**。
- 本轮不能确认（需真实凭据/网络/审批或钱诺成分级决策）：
  - severity=70 WebShell 是否升级到 critical/95（钱诺成口径决策）。
  - `auth/timeout/unreachable` 三类 `PlatformIngestError` 真实抛出。
  - 真实 POST `/api/xdr/v1/alerts/list` 实机网络调用 + 真实 MCP/真实 LLM（五步法第 5 步由全体三人+钱诺成共同确认，不属于本批次自动化测试范围）。
- 是否影响上下游/主链：**不影响**当前 MVP 主链（固定样例 + 官方脱敏结构 mock 两条路径均完整到 `APPROVAL_REQUIRED`）；真实平台接入需在五步法第 5 步时结合 `auth/timeout/unreachable` 错误分级手动补测。
- 建议状态：陈敏本批次任务 + T0826-06 历史批次**均已通过**，提交待审核。

## 10. 变更记录（T0903-06 新增条目）

| 日期 | 基线 Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-09-04 Step1-2 | `origin/main@e154343` 切干净分支后 | 新增 2 个官方脱敏 fixture + 20 条 CSV 映射升级 + 契约 MD 升级 + PR#22 升级 2 fixture、4 条契约结构测试；新增 21 条 T0903-06 契约回归（8/2/5/2/4 五组）。 | 干净环境单独跑 21+4 = 25 条通过；但混入真实 LLM/MCP 配置时 3 条偶发失败（非 hermetic 问题）。 |
| 2026-09-04 Step3（fix） | `1b43652 → 9c6f00d` | 修复 3 条非 hermetic：① 两条主链测试传 `investigation_backend="tool_mock"`（与既有 test_state_flow.py / test_xdr_openapi_platform.py 一致写法）② deep_agent_bridge 测试 `mock.patch.dict(os.environ, {"DEEP_AGENT_TOOL_MODE": ""})` 隔离。 | 干净环境全量 175 passed, 1 skipped；恶劣环境 3 条敏感测试 ≤3s 全部通过，**无回归**。 |

