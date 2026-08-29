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
| 真实 XDR OpenAPI 未接入 | 调用 `source="xdr"` 仍不具备真实路径、鉴权和字段映射。 | 不阻塞固定样例主链；阻塞真实平台演示。 | 获取接口资料后新增适配器并复测。 |
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
| 2026-08-27 | `main@4190550` / PR #22 `5ea5a53` | 新增脱敏 XDR 请求/响应结构、字段映射和输入契约测试；未触发真实平台调用。 | 新增契约测试 4 项通过；既有 JSONL/关联回归 17 项通过。 |
| 2026-08-28 | T0828-06 | 执行真实契约映射测试，验证真实响应解析、分页去重与专项规则。 | 真实契约测试 4 项通过；既有回归 17 项通过。 |

## 11. T0827-06 补充：真实 XDR 输入契约测试

本节追加于上述 T0826-06 测试记录之后。第 0—10 节中关于 2026-08-25 至 2026-08-26 的测试基线、8 个正式用例、专项 17 项、历史全量 79 项及固定 raw WebShell Mock 主链结果均保持原样，不能将其重新解释为本轮真实 XDR 验证。本轮在 `main@4190550` 的隔离环境中，仅新增无真实运行时实体的 XDR 输入契约检查，并复跑既有离线回归以确认契约材料不影响下游链路。

### 11.1 新增测试对象

| 测试对象 | 位置 | 本轮验证范围 | 不验证的内容 |
|---|---|---|---|
| 脱敏请求结构 | `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | 标明运行时本地传输边界、含时区时间窗口、筛选和提供方定义分页。 | 真实 URL、HTTP 方法、认证头、Token、页码/游标字段和请求执行。 |
| 脱敏响应结构 | `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | 最小记录字段、目的资产/来源设备规则、零记录语义和匿名证据引用。 | 真实事件、真实告警/资产 ID、原始响应和实际分页结果。 |
| 契约测试 | `tests/test_xdr_input_contract.py` | JSON 解析、结构占位边界、最低记录形状、资产/设备/零记录规则及非真实查询实体边界。 | 真实 XDR/MCP 连通、认证、性能、限流或网络重试。 |
| 已有下游回归 | `tests/test_jsonl_platform.py`、`tests/test_raw_jsonl_ingest_and_correlation.py`、`tests/test_alert_correlation_regression.py` | 固定 JSONL 标准化、映射、关联、证据和风险研判链路保持不变。 | 真实平台关联准确率、召回率或生产吞吐量。 |

### 11.2 新增用例与实际结果

| 用例 ID | 测试方法 | 预期结果 | 实际结果 | 状态 |
|---|---|---|---|---|
| `XDR-CT-001` | `test_request_declares_runtime_only_transport_and_pagination` | 请求结构声明 `PROVIDER_DEFINED_NOT_COMMITTED` 端点、仅本地受控认证、时间窗口和“页码或游标”待确认策略。 | 断言通过。 | Pass |
| `XDR-CT-002` | `test_response_carries_minimum_xdr_record_shape_without_real_identifiers` | 响应结构含最小 ID、时间、名称、等级、源/目的地址、数据源和证据字段；ID 仅为脱敏占位符。 | 断言通过。 | Pass |
| `XDR-CT-003` | `test_contract_preserves_existing_asset_and_empty_result_rules` | `destination_ip` 优先、`host_ip` 仅缺失回退；XDR 设备为 `source_device_name → data_source → XDR`；空结果为 `success_with_zero_records_not_transport_failure`。 | 断言通过。 | Pass |
| `XDR-CT-004` | `test_sample_never_claims_fixture_addresses_are_real_query_entities` | 样例明确不将固定地址视为真实查询实体，且无可用 XDR 配置或 `Bearer` 凭据。 | 断言通过。 | Pass |
| `XDR-CT-005` | 既有 JSONL/关联回归 | 保持 SQLi `high/80`、固定 WebShell 专项 `critical/95`、横向移动 `medium/65`、目的资产优先、15 分钟关联、证据引用和自动进入风险研判。 | 17 项测试返回 `OK`。 | Pass |
| `XDR-CT-006` | 真实 XDR 最小验证 | 在本地受控环境验证 schema、认证、只读权限、单条转换、分页去重和零记录/错误分类。 | 未执行。缺少真实 schema、认证方式与只读权限；当前代码亦没有 `xdr_openapi.py` 或 `source="xdr"` 实现路径。 | Blocked |

### 11.3 本轮实际执行命令与结果

```bash
# T0827-06 脱敏 XDR 输入契约测试
env -u APP_ENV -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_xdr_input_contract.py'

# T0827-06 对既有固定 JSONL/关联链路的保护性回归
env -u APP_ENV -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  PYTHONPATH=src python3 -m unittest \
  tests.test_jsonl_platform \
  tests.test_raw_jsonl_ingest_and_correlation \
  tests.test_alert_correlation_regression
```

实际输出分别为 `Ran 4 tests ... OK` 与 `Ran 17 tests ... OK`。两组测试均未访问网络、真实 XDR、真实 MCP 或真实业务数据。`XDR-CT-006` 的 Blocked 表示真实接入前置条件尚未具备，不代表前述固定 JSONL 主链或本轮脱敏契约测试失败。

### 11.4 与历史结果的关系及后续验收

本节新增结果不修改第 5 节统计的 T0826-06 正式用例数据；该表的“通过 8、失败 0、阻塞 0”仅对应当时已完成的固定 JSONL/MVP 用例。对于 T0827-06，本轮新增统计为：契约测试通过 4 项、下游保护性回归通过 17 项、真实 XDR 最小验证 Blocked 1 项、失败 0 项。历史的 2026-08-26 全量 79 项结果仍仅代表 `main@95defad` 加 PR #17 重放工作区的历史复验，不能写成当前 `main@4190550` 的全量复验结果。

真实接入日应先取得只读 schema、认证方式与允许查询范围，再在本地受控环境验证一条真实记录的稳定 ID、时间及时区、名称、等级、源/目的地址、资产、来源设备、证据标识和分页标记；随后验证跨页稳定 ID 去重，并区分 `success + zero_records`、`auth`、`timeout`、`platform_error` 和 `validation`。仅可提交脱敏结论；真实请求、响应、实体、URL、Token、Cookie、截图和 PCAP 均不进入仓库、文档、PR、CI 输出或群聊。

> 本轮通过的是“XDR 输入契约结构与现有下游链路兼容性”测试，不是“真实 XDR 平台已可用”测试。固定样例使用的 RFC 5737 地址不会命中真实 MCP/DBProxy；真实 MCP 的传输成功但业务零结果区分属于深度调查/MCP 模块后续实现，不在本次测试范围内。


## 12. 2026 年 8 月 29 日真实接入复验结果（T0828-06 真实字段映射）

### 12.1 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | `platform-tools`（平台工具） |
| 任务/测试批次 | `T0828-06`｜真实字段映射与输入质量处理收口。 |
| 执行人 | 陈敏 |
| 总体结论 | **通过（2026-08-29 实机复验）** |
| 关联正式交付章节 | `docs/deliverables/测试方案与测试报告.md` |
| 最后更新时间 | 2026-08-29 |

> 以下内容为 2026-08-29 真实联调反馈的脱敏记录。真实验证 ID、原始响应、请求头、认证材料和其他敏感值不得进入 GitHub、PR、CI 输出或群聊。

### 12.2 实机验证结论

根据《2026年8月29日真实XDR告警输入接入解决方案》，陈敏完成了对杨嘉琪提供的 **8 条真实非空告警** 的字段核对。实机验证使用的事件标识只保存在受控联调环境；本文不记录真实验证 ID，仅记录字段存在性、类型、枚举和映射关系。

- **映射状态**：`data.item` 单数列表提取正常；`uuId`、`lastTime`、`severity`、`hostIp` 等核心字段按已确认规则转换为现有 `NormalizedAlertRecord`/`AlertRecord`。
- **主链衔接**：真实告警具备进入风险研判和调查模块所需的标准化字段；未新增第二套上层告警对象。
- **敏感信息边界**：真实 URL、真实 IP、真实事件 ID、真实告警 ID、Token、Cookie、联动码、签名串和原始响应不进入仓库。

### 12.3 契约测试更新

运行 `tests/test_xdr_openapi_platform.py`，使用与 2026-08-29 实机响应一致的脱敏结构进行验证。

| 用例 ID | 类型 | 场景 | 结果 |
|---|---|---|---|
| `XDR-REAL-001` | 正常 | 验证 `data.item` 单数列表提取与 `uuId` 稳定标识映射。 | Pass |
| `XDR-REAL-002` | 正常 | 验证 `lastTime` Unix 时间戳转换。 | Pass |
| `XDR-REAL-003` | 正常 | 验证 `hostIp` 受影响资产优先级与 `dstIp` 目的地址映射。 | Pass |
| `XDR-REAL-004` | 安全 | 验证真实签名联调结果的受控记录边界；签名原文、签名结果和认证材料不写入仓库。 | Pass（实机联调记录） |

此外，本地自动化测试已覆盖认证失败、空结果、字段映射失败、超时 fallback、正常真实响应、分页、跨页去重和标准化记录进入关联主链。

### 12.4 变更记录追加

| 日期 | 基线 Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-28 | PR #28 | 真实字段映射契约测试。 | 4 项 Pass |
| 2026-08-29 | 联调收口 | **8 条真实记录实机复验**；更新 `data.item`、`uuId`、`lastTime`、`hostIp`/`dstIp` 结构测试。 | 通过 |

### 12.5 验收边界

本节的“8 条真实记录实机复验”来源于受控联调记录；本地自动化测试使用脱敏结构和 Mock HTTP，不将脱敏样例冒充真实平台查询结果。T0828-06 负责真实字段映射与输入质量处理；下游 T0828-07 负责统一候选研判、固定样例结果保留以及真实事件进入后的原始字段、规则输出和差异记录。
