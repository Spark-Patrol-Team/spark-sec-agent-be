# 告警接入与关联模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联） |
| 负责人 | 陈敏 |
| 文档状态 | T0903-06：真实 XDR 适配 + 58 项字段核对 + 175 passed 基线已补充。 |
| 实现状态 | 已复验 + 真实 XDR 适配完成；58 项逐字段核对（57 通过 1 待决策）；175 passed 基线。 |
| 能力性质 | 自研代码 + XdrOpenApiAdapter 真实只读接入 + 固定 JSONL fallback + Mock 主链。 |
| 关联任务/需求 | `T0826-06` 固定 JSONL 告警接入关联回归与文档补齐；`T0903-06` 真实输入契约资产迁移与 58 项字段核对（陈敏）。 |
| 关联正式交付章节 | `docs/deliverables/system-development-and-operation-guide.md`：第 8 章主流程说明、第 9 章模块说明与接入位置、第 11 章测试与验证。字段契约包：`docs/platform-tools/t0903-06-step2-contract-package.md`。 |
| 对应 PR 或 Commit | PR #17；PR#33 merge 点 `main@e154343`；T0903-06 提交 `9c6f00d`。 |
| 适用代码版本 | `9c6f00d`（T0903-06 最新提交；对应字段契约版本 `2026-09-03.t0903-chenmin-v1`）。 |
| 最后更新时间 | 2026-09-04（T0903-06：真实 XDR 接入、字段契约、下游摘要）。 |

## 1. 当前实现摘要

### 1.1 已实现

- `JsonlSampleAdapter` 在 `normalized` 模式下读取标准化固定样例，在 `raw` 模式下读取原始 JSONL 并调用 `RawJsonlNormalizer`。
- 原始样例可映射为 `NormalizedAlertRecord`，再适配为统一 `AlertRecord`。
- 固定映射支持 STA/XDR 来源设备、目的资产优先、`host_ip` 回退、WebShell 蚁剑专项 `critical/95` 与字段级证据引用。
- `AlertCorrelationService` 对同一候选活动执行事件类型、资产、来源设备和 15 分钟窗口校验，并输出 `SecurityEvent`。
- `Orchestrator` 在关联后调用风险研判；raw WebShell 固定样例可实际进入 `TRIAGED`、`APPROVAL_REQUIRED`，Mock 审批后到 `COMPLETED`。

### 1.2 未实现或未复验

- 真实 XDR OpenAPI 的网络超时、限流、客户端重试逻辑尚未独立于业务代码之外实现；当前仅做单次请求 + `PlatformIngestError.retryable` 标记。
- 真实平台上的跨窗口大批量关联（超过 `alert_max_pages=20` 的历史回溯）、真实吞吐、召回率和长时间窗口稳定性，因缺少真实标签和运行数据暂不可靠计算。
- 真实 XDR/MCP 的处置动作（阻断、隔离、封禁）和 MCP 写接口不在本模块范围内。

## 2. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/platforms/raw_jsonl.py` | `RawJsonlNormalizer` | 原始 STA/XDR JSONL 到 `NormalizedAlertRecord` 的映射与校验；含 `_xdr_severity` 数字严重度、`_xdr_event_type` 威胁分类六字段优先链、WebShell 专项升级。 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | 读取 raw/normalized 固定样例，生成 `AlertRecord`，提供证据查询 Mock。 |
| `src/sec_agent/platforms/xdr_openapi.py` | `XdrOpenApiAdapter`、`XdrOfficialSigner`、`_to_normalizer_raw`、`_extract_items`、`_alert_lookup_key` | 真实 XDR `POST /api/xdr/v1/alerts/list` 只读接入：官方签名、`{page,pageSize,startTimestamp}` 分页、`data.item` 单数响应解析、`uuId` 跨页去重、`lastTime → firstTime → updateTime` 时间优先、`srcIp[]/dstIp[]/srcPort[]/dstPort[]/traceBackId[]/devSourceName[]/engineName[]` 等数组首非空提取、52 类原始字段 `xdr_` 前缀留存。 |
| `src/sec_agent/services/ingest.py` | `AlertIngestService.ingest` | 按来源 `PLATFORM_BACKEND` 调用平台适配器；不重复解析来源字段。 |
| `src/sec_agent/services/correlation.py` | `AlertCorrelationService.correlate` | 执行最小关联（类型 + 资产 + 设备 + 15 分钟窗口）、四集合 `src_ips/dst_ips/assets/source_devices` 实体汇总和关联依据生成。 |
| `src/sec_agent/services/orchestrator.py` | `Orchestrator.start` | 接入→关联→风险研判→调查→处置的统一状态编排。真实路径需传 `investigation_backend="tool_mock"` 以保持测试 hermetic。 |
| `src/sec_agent/services/triage.py` | `RiskTriageService.triage` | 使用 `SecurityEvent` 与参与告警生成风险研判。 |
| `src/sec_agent/core/config.py` | `PLATFORM_BACKEND`、`XDR_*` 配置项 | 切换平台后端；配置 XDR 地址、鉴权方式（`auth_code`/`ak_sk`/`token`）、`alert_page_size`、`alert_max_pages`、`start_timestamp`、SSL 开关。 |
| `tests/fixtures/fixed_alerts/` | `raw_alerts.jsonl`、`normalized_alerts.jsonl`、`raw_to_normalized_mapping.csv`、`normalized_alert_schema.json` | 固定 JSONL 样例 + 31 条映射契约。 |
| `tests/fixtures/xdr_openapi/` | `official_desensitized_alert.json`、`official_desensitized_response.json` | T0903-06 新增：官方脱敏真实结构（来自 `XDR_OpenAPI更新版(1).md` 第五部分）与 `data.item` 分页壳。 |
| `tests/fixtures/xdr_contract/` | `xdr_list_alerts_request_sanitized.json`、`xdr_list_alerts_response_sanitized.json` | PR#22 升级迁入：POST 请求契约 + `item[]/camelCase/severity:int/Unix秒戳/数组字段` 响应契约。 |
| `docs/modules/platform-tools/xdr_field_mapping.csv` | 20 条官方字段映射（CSV） | PR#22 升级迁入：001-014（原始占位符→官方 camelCase 升级）+ 015-020（新增 T0903-06 契约条目：原始留存/分页/签名/去重/错误分级/severity 遗留）。 |
| `docs/modules/platform-tools/xdr_input_contract.md` | 完整输入契约文档 | PR#22 升级迁入：§3 数据流图、§4 映射表（带 PR#22→PR#33 演变标注）、§6 双列对比、§7 PlatformIngestError 六类分级。 |
| `docs/platform-tools/t0903-06-step2-contract-package.md` | 字段契约包 | 四模型（AlertRecord/NormalizedAlertRecord/SecurityEvent/EventContext）逐字段契约。 |
| `tests/test_alert_correlation_regression.py` | `AlertCorrelationRegressionTest` | T0826-06 关联专项回归（5 条）。 |
| `tests/test_raw_jsonl_ingest_and_correlation.py` | `RawJsonlIngestAndCorrelationTest` | T0826-06 原始 JSONL 接入与关联回归（6 条）。 |
| `tests/test_jsonl_platform.py` | `JsonlSamplePlatformTest` | T0826-06 JSONL 适配器主链回归（6 条）。 |
| `tests/test_t0903_06_contract_regression.py` | `T090306DesensitizedRealConversionTest`（8）+ `FixedSampleRegression`（2）+ `MissingFieldTest`（5）+ `EmptyResultTest`（2）+ `DeduplicationTest`（4） | T0903-06 新增：21 条契约回归（5 类场景）。 |
| `tests/test_xdr_input_contract.py` | `XdrInputContractTest` | PR#22 升级迁入：4 条契约结构测试（请求/响应/适配器/脱敏约束）。 |
| `tests/test_xdr_openapi_platform.py` | `XdrOpenApiPlatformTest` | XDR OpenAPI 适配器的单独专项回归（签名/分页/去重/字段映射/错误分级）。 |

## 3. 依赖与配置

| 名称 | 必需/可选 | 获取方式 | 未配置时行为 |
|---|---|---|---|
| Python `>=3.11` | 必需 | 按 `pyproject.toml` 与团队运行说明配置。 | 无法运行项目测试和主流程。 |
| `PLATFORM_BACKEND=jsonl_sample` / `fixed_sample` / `xdr_openapi` | 运行时必需 | `.env` 或命令行环境变量。 | 默认可用 `fixed_sample`；`xdr_openapi` 会走真实 POST 接口。 |
| `JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts` | `jsonl_sample` 时必需 | 相对项目根目录配置。 | 样例文件缺失时读取失败。 |
| `JSONL_INPUT_MODE=normalized\|raw` | `jsonl_sample` 时可选 | `.env` 或命令行环境变量。 | 默认 `normalized`；`raw` 走标准化器 `RawJsonlNormalizer`。 |
| `STORAGE_BACKEND=memory` | 本地演示可选 | `.env` 或命令行环境变量。 | 默认内存存储；不需要 MySQL。 |
| `XDR_BASE_URL`、`XDR_AUTH_CODE`（或 `XDR_ACCESS_KEY` + `XDR_SECRET_KEY`，或 `XDR_TOKEN`） | `xdr_openapi` 必填 | 受控环境变量或本地受控配置，**不得进入仓库**。 | 缺任一必填项 `XdrOfficialSigner` 拒绝启动，不降级。 |
| `XDR_ALERT_PAGE_SIZE`（默认 50） / `XDR_ALERT_MAX_PAGES`（默认 20） / `XDR_START_TIMESTAMP` | 可选（`xdr_openapi`） | 环境变量或 `core/config.py`。 | 默认值足够 MVP 单次事件查询。 |
| `XDR_VERIFY_SSL=false`（当前默认与官方对齐） | 可选（`xdr_openapi`） | 配置。 | 若真实证书链正确可切 `true`。 |
| 深信服 MCP 地址 | 可选 | 受控环境变量或本地受控配置。 | 测试框架跳过依赖真实 MCP 的 1 项测试；固定 JSONL 和 Mock 主链不受影响。 |
| `TZ=Asia/Shanghai` | 强烈推荐（CI/生产必配） | 系统或容器时区 / 进程启动前 `$env:TZ='Asia/Shanghai'`。 | **隐含部署假设**：当前 `fromtimestamp()` 取本地墙钟再补上海时区，UTC 默认服务器会导致 occurred_at 偏移 8 小时，破坏 15 分钟关联窗口。 |
| `DEEP_AGENT_TOOL_MODE`、`LLM_BASE_URL`、`LLM_API_KEY`、`llm_config.local.json` | 可选但测试需隔离 | 真实生产可能存在；**测试运行前必须清除或显式 pin 后端**，否则 auto 调查后端会尝试真实 LLM/MCP，导致非确定与超时。 | 主链测试统一传 `investigation_backend="tool_mock"`；`test_deep_agent_bridge` 需 `mock.patch.dict(os.environ, {"DEEP_AGENT_TOOL_MODE": ""})` 隔离。 |

- 支持的运行环境：项目声明 Python `>=3.11`；本轮使用 Python 3.12 Windows + Ubuntu CI 双实测。
- 敏感配置只通过环境变量或受控配置注入；文档、代码、固定样例和契约 fixture 中不得填写真实凭据、Token、接入码、MCP URL、Cookie 或内网地址。

## 4. 启动与调试

在仓库根目录执行（示例以 **Windows PowerShell** 为主，与当前陈敏开发环境一致；Linux bash 可参考历史 bash 版本）：

```powershell
# 0. 预先设置 Python 包路径（所有命令共用）
$env:PYTHONPATH = "src;" + $env:PYTHONPATH

# —— T0826-06 固定 JSONL 专项回归（历史批次）
python -m pytest tests/test_alert_correlation_regression.py tests/test_raw_jsonl_ingest_and_correlation.py tests/test_jsonl_platform.py -v

# —— T0903-06 新增：契约回归 21 条 + PR#22 升级契约 4 条（真实 XDR 字段/脱敏结构/缺字段/空结果/去重）
python -m pytest tests/test_t0903_06_contract_regression.py tests/test_xdr_input_contract.py -v

# —— XDR OpenAPI 适配器专项（签名/分页/数据.item单数/uuId去重/严重度数字映射/lastTime优先）
python -m pytest tests/test_xdr_openapi_platform.py -v

# —— 全量测试（干净环境，推荐）
#    清除会触发真实 LLM/MCP 的环境变量，保证 hermetic
$env:LLM_BASE_URL = ""; $env:LLM_API_KEY = ""; $env:DEEP_AGENT_TOOL_MODE = ""
python -m pytest tests/ -v 2>&1 | Select-Object -Last 30
#    预期: 175 passed, 1 skipped (test_web_shell_full_run 需真实 LLM key)

# —— 恶劣环境验证（模拟开发机上存在真实 LLM/MCP 配置的最不利情况）
$env:LLM_BASE_URL = "https://example.fake.invalid/v1"; $env:LLM_API_KEY = "sk-fake-not-real"; $env:DEEP_AGENT_TOOL_MODE = "mcp"
python -m pytest tests/test_t0903_06_contract_regression.py::T090306DesensitizedRealConversionTest::test_full_main_chain_to_approval_required tests/test_t0903_06_contract_regression.py::T090306FixedSampleRegressionTest::test_fixed_sample_main_chain_to_approval_required tests/test_deep_agent_bridge.py::DeepAgentBridgeTest::test_deep_agent_backend_maps_external_report_to_domain_report -v
#    预期: 3 passed，且不超过 3 秒（不再等待 LLM 超时）

# —— raw WebShell 固定 JSONL 最小主链
$env:APP_ENV = "local"; $env:STORAGE_BACKEND = "memory"; $env:PLATFORM_BACKEND = "jsonl_sample"; $env:JSONL_INPUT_MODE = "raw"; $env:JSONL_SAMPLE_DIR = "tests/fixtures/fixed_alerts"
python -m sec_agent.scripts.run_flow
```

- 成功判据：
  - **T0826-06 专项** 17 passed
  - **T0903-06 + PR#22 契约** 25 passed
  - **全量** 175 passed, 1 skipped；恶劣环境下 3 条 hermetic 修复点全过且不超时
  - **raw WebShell 主链** 依次 `RECEIVED → CORRELATING → TRIAGED → INVESTIGATING → DECISION_READY → APPROVAL_REQUIRED`；Mock 审批通过后 `EXECUTING → VERIFYING → COMPLETED`
- 常见失败及排查：
  - 出现 `DeepAgentBridgeUnavailable` 或状态没到 `APPROVAL_REQUIRED`：环境变量没清干净（`DEEP_AGENT_TOOL_MODE`/`LLM_API_KEY`），或者测试没传 `investigation_backend="tool_mock"`
  - occurred_at 错位 8 小时 / 15 分钟窗口断言偶发失败：检查 `TZ`，确保开发/CI 统一为 `Asia/Shanghai`
  - 样例找不到：检查 `JSONL_SAMPLE_DIR` 是否为 **仓库根** 相对路径，不是相对于 `src/`
  - Python 版本 < 3.11：安装合规解释器，**不要用 3.9 强跑**（会因 `list[X]` 语法崩溃）

## 5. 调用与接入方法

### 5.1 调用入口

- 主链入口：`Orchestrator.start(StartRunRequest(source="jsonl_sample", sample_id="FIX-XDR-WEBSHELL-001"))`。
- 接入入口：`AlertIngestService.ingest` 调用 `JsonlSampleAdapter.fetch_alerts`。
- 关联入口：`AlertCorrelationService.correlate(alerts)`。
- 证据查询入口：JSONL 适配器的 `evidence_lookup` Mock 工具，根据 `SecurityEvent.alert_refs` 查询字段级 `evidence_refs`。

### 5.2 最小示例

```python
from pathlib import Path
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
from sec_agent.services.correlation import AlertCorrelationService

adapter = JsonlSampleAdapter(Path("tests/fixtures/fixed_alerts"), input_mode="raw")
alerts = adapter.fetch_alerts(sample_id="FIX-XDR-WEBSHELL-001")
event = AlertCorrelationService(window_minutes=15).correlate(alerts)
```

```text
SecurityEvent：
- alert_refs: ["FIX-XDR-WEBSHELL-001"]
- entities.assets: ["198.51.100.11"]
- event_count_after: 1
- correlation_reason: 包含事件类型、资产、设备和时间窗口
```

### 5.3 上下游接入注意事项

- 所有平台字段先在 `platforms/` 适配，不要在 `services/correlation.py` 重复解析 JSON。
- 关联前的告警必须具有一致事件类型、受影响资产和来源设备；不一致时由上层拆分事件。
- 关联模块不直接写状态，必须由 `orchestrator.py` 推进 `EventContext`。
- `sample_nature` 必须保留，避免将合成回归样例混入平台字段派生样例展示。

## 6. 异常处理与安全控制

- 输入错误：空告警、样例不存在、`sample_id/xdr_event_id` 冲突、事件类型/资产/设备冲突和 15 分钟窗口超时均返回可读异常。
- 依赖或工具失败：固定 JSONL 读取错误会使编排器记录 `ingest` 或 `orchestrator` 错误；真实平台依赖未接入，不进行伪造 fallback。
- 重复调用与幂等：关联为纯内存计算；后续审批和 Mock 处置的幂等由 `EventRepository` 与 `idempotency_key` 管理。
- 超时、重试与回滚：固定样例关联未实现网络超时/重试/回滚；真实平台接入时必须单独实现和测试。
- 权限、审批与敏感数据：关联不访问真实凭据也不触发外部动作；高风险处置仍由后续响应模块走人工审批；证据仅保留引用。

## 7. 真实平台、Mock 与 fallback 边界

| 能力 | 当前实际实现 | 触发条件 | 不得误写为 |
|---|---|---|---|
| 原始/标准化告警读取 | 固定 JSONL fallback + **真实 XDR OpenAPI 只读接入**（POST、官方签名、分页、去重、字段映射） | `PLATFORM_BACKEND=jsonl_sample` / `xdr_openapi` | “已实时拉取真实 MCP 告警”；真实路径仅只读，不执行处置写入。 |
| STA/XDR 字段映射 | 本地 `RawJsonlNormalizer` + `XdrOpenApiAdapter._to_normalizer_raw`（与 CSV 20 条契约对齐） | `JSONL_INPUT_MODE=raw` / `PLATFORM_BACKEND=xdr_openapi` | “已调用真实 STA/XDR 管理面写入接口”。 |
| 证据查询 | JSONL 字段级 Mock + XDR 响应的 `traceBackId[]` 映射为证据引用 + 原始字段 `xdr_*` 前缀留存 | 调用 `evidence_lookup` 或检查 `AlertRecord.evidence_refs` / `scenario_fields` | “已获得真实平台原始日志流、PCAP 或工单”。 |
| 风险研判衔接 | 自研主链代码：真实 XDR `SecurityEvent` 进入 `RiskTriageService`，风险分使用 `severity → risk_score_seed`（数字优先） | 关联成功后由 `Orchestrator` 调用 | “已验证所有真实告警的真实人工研判结论”；当前为固定规则风险种子，不替换人工研判。 |
| 处置和验证 | 有状态 Mock | 高风险样例审批通过后 | “已在真实资产执行隔离/封禁”；不绕过审批。 |
| 真实 XDR OpenAPI 分页/限流/客户端重试 | **当前最小实现**：`page + pageSize + startTimestamp` 页码式分页，`total`/`alert_max_pages` 双重终止；错误统一 `PlatformIngestError.retryable` 标记。 | `PLATFORM_BACKEND=xdr_openapi` | “已实现完备的限流、指数退避、断点续传和死信队列”。 |
| 调查后端确定性（hermetic 测试） | 所有合约/回归主链测试必须显式传 `investigation_backend="tool_mock"` | Orchestrator 启动时指定 | “真实 LLM/MCP 的调查结果与本模块测试一致”。 |

## 8. 已知限制与待办

| 优先级 | 事项 | 是否影响主链 | 负责人/完成条件 |
|---|---|---|---|
| P0 | `severity` 数字路径与 WebShell 字符串专项升级语义未统一：固定样例 `FIX-XDR-WEBSHELL-001` 为 `critical/95`，真实 XDR `severity=70` 的 WebShell 仅到 `high/80`。 | 影响风险分差 15，不阻塞状态流转。 | 钱诺成决策后（70 是否等价"高危"）由陈敏改 `RawJsonlNormalizer._xdr_severity()`。 |
| P0 | `TZ=Asia/Shanghai` 隐含部署假设：UTC 环境下 occurred_at 偏移 8 小时，会破坏 15 分钟关联窗口。 | 不阻塞 Windows 本地；阻塞 CI/生产 Linux 默认 UTC。 | 部署文档与 CI workflow 统一设置 `TZ`。 |
| P1 | 真实 XDR 客户端超时、限流、指数退避重试未独立于 `XdrOpenApiAdapter.fetch_alerts()` 之外封装。 | 不影响固定样例；影响真实接入稳定性。 | 真实联调阶段由平台适配负责人补齐。 |
| P1 | 调查查询中，空实体集合（`src_ips/dst_ips/assets`）会导致 MCP 参数缺失，当前依赖下游摘要的替代查询维度。 | 不阻塞主链状态流转；影响调查 Agent 自动取数。 | 杨景凡侧补齐 `evidence_gaps` 填充。 |
| P1 | 跨 `alert_max_pages=20` 的历史回溯（批量长时间窗口）会被强制截断。 | 不阻塞 MVP 单次事件；阻塞大批次场景。 | 增大上限或改为滚动时间窗口。 |
| P2 | 攻击图谱、跨资产聚类、概率关联暂未实现。 | 不影响当前最小关联。 | 获得稳定标签与评估数据后扩展。 |

## 9. 运行观测、版本兼容与迁移

- 日志与关键指标位置：当前 MVP 主要通过 `EventContext.timeline`、`errors`（含 `PlatformIngestError` 六类错误：`auth/platform_error/field_mapping/empty_result/timeout/unreachable`）、`alert_refs`（真实 uuId）、`event_summary` 和测试输出观测；未实现独立监控指标/集中日志平台。
- 健康检查或运行状态判断：主流程关注 `status`、`timeline`、`triage.risk_score`、`response.execution` 和 `response.verification`；HTTP 服务健康检查见 `GET /health`。
- 兼容的接口/Schema/平台版本：
  - 固定样例契约 `NormalizedAlertRecord` schema_version = `2026-08-21.mvp.v1`
  - 真实 XDR 契约版本 = `2026-09-03.t0903-chenmin-v1`（字段契约包版本，含 `uuId` 唯一 / `lastTime→firstTime→updateTime` / `severity int` / `srcIp[]→dstIp[]` / 威胁分类六字段优先链 / `data.item` 单数分页 等约定）
  - PR#22 CSV 20 条映射（001-014 升级字段名 + 015-020 新契约条目）
- 升级、迁移或回退注意事项：
  - 调整字段映射、风险种子或关联条件 **必须** 同步更新：① `docs/modules/platform-tools/xdr_field_mapping.csv` ② `tests/fixtures/fixed_alerts/raw_to_normalized_mapping.csv` ③ 契约回归测试 ④ `docs/modules/platform-tools/xdr_input_contract.md`
  - 真实平台适配器应 **新增实现**（新增 platforms/*.py 或扩展 xdr_openapi.py），**不得破坏** `PlatformAdapter` 协议 / `AlertRecord` / `SecurityEvent` 模型 / `StartRunRequest` 契约
  - 回退 T0903-06：只要保留 `9c6f00d` 提交的 2 个 fixture + 25 条契约测试，即可单独回退代码
  - Windows 与 Linux 迁移：注意 `TZ=Asia/Shanghai` 环境变量，Windows 上可选 `pip install tzdata` 保证 `zoneinfo` 能找到上海时区（部分原生 Python 3.11 Windows 可能缺）

## 10. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-25 | PR #17 / `1a5bbf1` | 新增告警关联专项回归 + 固定 JSONL 主链验证。 | `tests/test_alert_correlation_regression.py`、`test_raw_jsonl_ingest_and_correlation.py`、`test_jsonl_platform.py`。 |
| 2026-08-25 | PR #17 后续提交 | 对齐团队开发说明模板：补运行/配置/调用/异常/安全/边界/限制/兼容性。 | 文档事实对照 GitHub main 基线复核。 |
| 2026-08-26 | `95defad` + PR #17 重放 | 最新 main 复验固定 JSONL 接入/关联/主链调用。 | 专项 17 项、全量 79 项通过，框架 skipped 1；raw WebShell 主链到 `COMPLETED`。 |
| 2026-09-04（T0903-06 新增） | `main@e154343` → 分支 `chenmin/t0903-6-origin-main-clean` → 提交 `9c6f00d` | **真实 XDR 只读接入与契约迁移补齐**：① 从 origin/main 建干净分支，迁入 PR#22 4 个契约资产（CSV 20 条/契约 MD/xdr_contract 2 fixture + 4 条升级后契约测试）并升级占位符字段为官方 camelCase；② 新增 T0903-06 21 条契约回归（脱敏转换 8/固定样例 2/缺字段 5/空结果 2/去重 4）；③ 修复 3 条非 hermetic 测试（主链两条 + deep_agent 桥接一条）传 `investigation_backend="tool_mock"` / 打 `os.environ` patch；④ 补 2 份下游摘要（给闫昱硕研判/给杨景凡调查）+ 前三步存档 MD。 | 最终基线 **175 passed, 1 skipped**；其中：`test_t0903_06_contract_regression.py` = 21，`test_xdr_input_contract.py` = 4，两项合计 25 条新增且全绿；恶劣环境（LLM 伪配置 + DEEP_AGENT_TOOL_MODE=mcp）下 3 条敏感测试 ≤3 秒通过（之前 26.5 秒且偶发失败）。 |
