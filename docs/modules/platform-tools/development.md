# 告警接入与关联模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 真实字段确认 |
| 负责人 | 陈敏 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 + 固定 JSONL fallback + Mock 主链；真实 XDR/MCP 未接入。 |
| 关联任务/需求 | `T0828-06` |
| 关联正式交付章节 | `docs/deliverables/系统开发与运行说明.md`：第 8 章主流程说明、第 9 章模块说明与接入位置、第 11 章测试与验证。 |
| 对应 PR 或 Commit | PR #34。 |
| 适用代码版本 | `main` 。 |
| 最后更新时间 | 2026-0830 |

## 1. 当前实现摘要

### 1.1 已实现

- `JsonlSampleAdapter` 在 `normalized` 模式下读取标准化固定样例，在 `raw` 模式下读取原始 JSONL 并调用 `RawJsonlNormalizer`。
- 原始样例可映射为 `NormalizedAlertRecord`，再适配为统一 `AlertRecord`。
- 固定映射支持 STA/XDR 来源设备、目的资产优先、`host_ip` 回退、WebShell 蚁剑专项 `critical/95` 与字段级证据引用。
- `AlertCorrelationService` 对同一候选活动执行事件类型、资产、来源设备和 15 分钟窗口校验，并输出 `SecurityEvent`。
- `Orchestrator` 在关联后调用风险研判；raw WebShell 固定样例可实际进入 `TRIAGED`、`APPROVAL_REQUIRED`，Mock 审批后到 `COMPLETED`。

### 1.2 未实现或未复验

- 真实 XDR OpenAPI/MCP 鉴权、实时查询、分页、限流、网络超时、重试和返回字段映射未实现。
- 真实平台上的关联准确率、召回率、性能吞吐量和长时间窗口稳定性未具备可靠计算条件。

## 2. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/platforms/raw_jsonl.py` | `RawJsonlNormalizer` | 原始 STA/XDR JSONL 到 `NormalizedAlertRecord` 的映射与校验。 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | 读取 raw/normalized 固定样例，生成 `AlertRecord`，提供证据查询 Mock。 |
| `src/sec_agent/services/ingest.py` | `AlertIngestService.ingest` | 按来源调用平台适配器；不重复解析来源字段。 |
| `src/sec_agent/services/correlation.py` | `AlertCorrelationService.correlate` | 执行最小关联、实体汇总和关联依据生成。 |
| `src/sec_agent/services/orchestrator.py` | `Orchestrator.start` | 接入→关联→风险研判→调查→处置的统一状态编排。 |
| `src/sec_agent/services/triage.py` | `RiskTriageService.triage` | 使用 `SecurityEvent` 与参与告警生成风险研判。 |
| `tests/test_alert_correlation_regression.py` | `AlertCorrelationRegressionTest` | T0826-06 关联专项回归。 |

## 3. 依赖与配置

| 名称 | 必需/可选 | 获取方式 | 未配置时行为 |
|---|---|---|---|
| Python `>=3.11` | 必需 | 按 `pyproject.toml` 与团队运行说明配置。 | 无法运行项目测试和主流程。 |
| `PLATFORM_BACKEND=jsonl_sample` | 运行固定 JSONL 主链时必需 | `.env` 或命令行环境变量。 | 默认可改用 `fixed_sample`，但不走 JSONL 路径。 |
| `JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts` | 运行固定 JSONL 时必需 | 相对项目根目录配置。 | 样例文件缺失时读取失败。 |
| `JSONL_INPUT_MODE=normalized|raw` | 运行 JSONL 时可选 | `.env` 或命令行环境变量。 | 默认 `normalized`；`raw` 走标准化器。 |
| `STORAGE_BACKEND=memory` | 本地演示可选 | `.env` 或命令行环境变量。 | 默认内存存储；不需要 MySQL。 |
| 深信服 MCP 地址 | 可选 | 受控环境变量或本地受控配置。 | 测试框架跳过依赖真实 MCP 的 1 项测试；固定 JSONL 和 Mock 主链不受影响。 |

- 支持的运行环境：项目声明 Python `>=3.11`；本轮使用 Python 3.12 实测。
- 敏感配置只通过环境变量或受控配置注入；文档、代码和固定样例中不填写真实凭据、Token、接入码、MCP URL 或内网地址。

## 4. 启动与调试

在仓库根目录执行：

```bash
# 专项回归
PYTHONPATH=src python -m unittest tests.test_alert_correlation_regression

# JSONL 接入和关联相关回归
PYTHONPATH=src python -m unittest \
  tests.test_alert_correlation_regression \
  tests.test_raw_jsonl_ingest_and_correlation \
  tests.test_jsonl_platform

# 全量测试；外部环境变量干扰配置测试时可先清除相关变量
env -u APP_ENV -u APP_NAME -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  -u JSONL_SAMPLE_DIR -u STORAGE_BACKEND \
  PYTHONPATH=src python -m unittest discover -s tests

# raw 固定 JSONL 主链
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample \
JSONL_INPUT_MODE=raw JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts \
PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

- 成功判据：专项关联回归通过；全量测试返回 `OK`；raw WebShell 主链依次记录 `RECEIVED`、`CORRELATING`、`TRIAGED`、`APPROVAL_REQUIRED`，Mock 审批后最终为 `COMPLETED`。
- 常见失败及排查：样例文件不存在时检查 `JSONL_SAMPLE_DIR`；`APP_ENV=PROD` 等外部变量导致配置枚举不匹配时使用本地配置或清除变量；Python 版本不满足时安装/启用合规解释器，不使用 Python 3.9 强行运行。

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
| 原始/标准化告警读取 | 固定 JSONL fallback | `PLATFORM_BACKEND=jsonl_sample` | “已实时拉取 XDR 告警”。 |
| STA/XDR 字段映射 | 本地实现 | `JSONL_INPUT_MODE=raw` | “已调用真实 STA/XDR 接口”。 |
| 证据查询 | JSONL 字段级 Mock | 调用 `evidence_lookup` | “已获得真实平台原始日志”。 |
| 风险研判衔接 | 自研主链代码 | 关联成功后由编排器调用 | “已验证所有真实告警风险”。 |
| 处置和验证 | 有状态 Mock | 高风险样例审批后 | “已执行真实隔离/封禁”。 |
| 真实 XDR OpenAPI/MCP | 未实现 | 不适用 | “已完成平台正式接入”。 |

## 8. 已知限制与待办

| 优先级 | 事项 | 是否影响主链 | 负责人/完成条件 |
|---|---|---|---|
| P0 | 真实 XDR OpenAPI 路径、鉴权和返回字段映射未确认。 | 不影响固定 JSONL 主链；影响真实平台演示。 | 平台接口资料明确后，由平台适配器负责人实现。 |
| P1 | 未实现跨资产、跨设备和跨场景攻击图谱。 | 不影响当前最小关联。 | 获得评估数据和业务规则后扩展。 |
| P1 | 真实平台超时、限流和重试未实现。 | 不影响固定样例。 | 真实客户端开发时补齐。 |

## 9. 运行观测、版本兼容与迁移

- 日志与关键指标位置：当前 MVP 主要通过 `EventContext.timeline`、`errors`、`alert_refs`、`event_summary` 和测试输出观测；未实现独立监控指标或集中日志平台。
- 健康检查或运行状态判断：主流程关注 `status`、`timeline`、`triage.risk_score`、`response.execution` 和 `response.verification`；HTTP 服务健康检查见 `GET /health`。
- 兼容的接口/Schema/平台版本：固定样例契约为 `NormalizedAlertRecord`，`schema_version=2026-08-21.mvp.v1`；仅支持仓库内固定 JSONL 结构。
- 升级、迁移或回退注意事项：调整字段映射、风险种子或关联条件时必须同步更新固定 JSONL、映射说明和回归测试；真实平台适配器应新增实现，不应破坏 `PlatformAdapter` 与 `AlertRecord` 契约。

## 10. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-25 | PR #17 / `1a5bbf1` | 新增告警关联专项回归与固定 JSONL 主链验证。 | `tests/test_alert_correlation_regression.py`、`test_raw_jsonl_ingest_and_correlation.py`、`test_jsonl_platform.py`。 |
| 2026-08-25 | PR #17 后续提交 | 对齐团队开发说明模板，补充运行、配置、调用、异常、安全、边界、限制与兼容性信息。 | 文档事实对照同一 GitHub main 基线复核。 |
| 2026-08-26 | PR #17 后续联调提交 | 在最新 `main@95defad` 上重放 PR #17，复验 JSONL 固定样例接入、关联和主链调用。 | 专项 17 项、全量 79 项通过，框架 skipped 1；raw WebShell 主链到 `COMPLETED`。 |
| 2026-08-27 | PR #22 / `5ea5a53` | 在不改动上述 8 月 25—26 日历史内容和变更记录的前提下，新增真实 XDR 输入契约、字段映射、脱敏结构样例及接入前验证准备；未新增真实客户端代码。 | `test_xdr_input_contract.py` 4 项通过；既有 JSONL/关联回归 17 项通过。 |
| 2026-08-30 | PR #34 | 新增真实 XDR 字段映射与输入质量补充。 | 专项测试 13 passed；完整测试 143 passed, 1 skipped。 |

## 11. T0827-06 补充：真实 XDR 输入适配准备

本节追加于原开发说明之后，原有 `raw_jsonl.py`、`jsonl_sample.py`、`AlertIngestService`、`AlertCorrelationService`、`Orchestrator` 和风险研判实现说明均继续有效。本轮交付不修改 `src/` 目录中的平台读取、关联、调查或 MCP 代码；它提供真实 XDR 接入实施前的输入契约和回归护栏，使未来适配器能够以 PR #17 已复验的下游链路为目标接入。

### 11.1 当前代码边界

当前 `src/sec_agent/platforms/base.py` 已定义 `PlatformAdapter.fetch_alerts(sample_id, xdr_event_id)` 这一统一读取边界。`src/sec_agent/platforms/raw_jsonl.py` 负责固定 raw JSONL 到 `NormalizedAlertRecord` 的受控标准化，`src/sec_agent/platforms/jsonl_sample.py` 负责 raw/normalized 固定样例到 `AlertRecord` 的适配；二者是离线 fallback 和回归实现，不是 XDR OpenAPI 客户端。

`src/sec_agent/services/ingest.py` 对 `source="xdr"` 仍抛出 `NotImplementedError`，原因是 XDR OpenAPI 路径、鉴权和字段映射尚未确认；容器层也没有注册 `PLATFORM_BACKEND=xdr_openapi`。因此，PR #22 当前实现状态应表述为“**真实 XDR 输入契约与脱敏样例已准备，真实读取适配器尚未实现**”，不能表述为真实接口已连通。

### 11.2 本轮新增材料与实施作用

| 文件 | 作用 | 与既有实现的衔接 |
|---|---|---|
| `docs/modules/platform-tools/xdr_input_contract.md` | 定义真实 XDR 的最小输入、必填/可选字段、错误、零记录、分页、去重、脱敏与接入日验收规则。 | 规定未来适配器输出应满足 `NormalizedAlertRecord`/`AlertRecord` 的下游语义。 |
| `docs/modules/platform-tools/xdr_field_mapping.csv` | 提供 14 条机器可读映射，包括来源确定性、缺失处理和敏感信息限制。 | 历史结构已确认字段和接入日候选字段分列；候选字段不得当作厂商官方 schema。 |
| `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | 表达含时区时间窗口、筛选、分页和本地认证边界的请求结构。 | 不包含可执行端点、认证头或凭据。 |
| `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | 表达最小记录、分页、零记录和证据引用结构。 | 使用语义化占位符和 RFC 5737 文档地址，不是平台原始响应。 |
| `tests/test_xdr_input_contract.py` | 验证上述结构、字段规则、资产/设备回退和脱敏边界。 | 防止后续真实适配器的字段设计破坏既有回归契约。 |

### 11.3 未来适配器的最小实现顺序

1. 平台负责人仅在本地受控环境确认只读 XDR schema、认证、TLS、允许查询范围、分页模型和限流约束，不向仓库、PR 或群聊提交真实值。
2. 新增独立的 `src/sec_agent/platforms/xdr_openapi.py`，实现 `PlatformAdapter.fetch_alerts(...)`。该适配器只能负责请求构造、响应解析、固定时间窗口、分页、稳定 ID 去重、字段标准化、结构化错误和受控证据引用。
3. 按 [xdr_field_mapping.csv](xdr_field_mapping.csv) 将输入转换为 `NormalizedAlertRecord` 或等价标准化对象，再输出与现有 `JsonlSampleAdapter` 相同语义的 `AlertRecord`。下游 `services/` 不应直接解析厂商 JSON。
4. 强制保持既有规则：稳定 ID、可解析且带时区的时间、非空告警名称、可映射严重性、来源设备和最少一个审计证据引用为最小条件；`destination_ip` 优先，只有缺失时回退 `host_ip`；XDR 优先 `source_device_name`，再回退 `data_source`，最终回退 `XDR`。
5. 不得将固定专项规则扩展为通用平台规则：SQLi 保持 `high/80`，横向移动保持 `medium/65` 和 `synthetic_regression`；仅“WebShell蚁剑工具文件管理 + 高危”的固定专项样例为 `critical/95`。真实 XDR 严重性必须由接入日确认的枚举经受控词典映射。
6. 在容器层注册真实后端前，补充认证、超时、平台错误、响应校验、分页、跨页去重和零记录测试，然后复跑原有固定 JSONL/关联回归，确认真实输入只替换上游来源而不破坏现有链路。

### 11.4 错误、零记录与 MCP 分工

真实 XDR 读取中，认证/授权失败应分类为 `auth`；网络问题为 `timeout`；非成功响应和结构解析失败分别为 `platform_error`/`validation`。请求成功而 `records=[]` 必须记为 `success + zero_records`，既不是连接失败，也不得产生虚构告警或 `SecurityEvent`。读取型网络重试只能在固定时间窗口与同一幂等审计上下文内执行。

真实 MCP 的“传输成功但业务空结果”与“连接/认证失败”的进一步代码区分，属于深度调查/MCP 负责人后续的专门改动；本轮不修改该模块，也不将固定样例 RFC 5737 地址用于真实 MCP 查询。这样可避免把平台数据可用性、调查证据不足和固定样例降级路径混为同一问题。

### 11.5 本轮实际验证

本轮已在隔离环境执行以下命令，未访问真实 XDR、真实 MCP 或网络：

```bash
env -u APP_ENV -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_xdr_input_contract.py'

env -u APP_ENV -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  PYTHONPATH=src python3 -m unittest \
  tests.test_jsonl_platform \
  tests.test_raw_jsonl_ingest_and_correlation \
  tests.test_alert_correlation_regression
```

第一组命令运行 4 项 XDR 脱敏契约测试并返回 `OK`；第二组命令运行 17 项固定 JSONL/关联回归并返回 `OK`。这些结果只证明契约材料可解析且没有破坏既有离线主链，不证明真实 XDR API、真实 MCP、真实分页、认证或性能已经完成验证。

## 11. T0828-06 真实 XDR 字段映射与输入质量补充（2026-08-30）

本节在陈敏负责的 PR #22 历史开发说明基础上追加，不删除或改写此前内容。本次实现以回归后的最新 `main` 为基线，仅补充真实 XDR 响应解析、标准化、输入质量和兼容性测试，不接手 PR #28 中未经官方材料确认的 `auth_code` 鉴权或请求代码。

适配器对已确认真实结构进行字段解析：从 `data.item` 提取列表，使用 `uuId` 作为稳定标识，支持 `firstTime/lastTime` 秒/毫秒时间戳，支持数值或文本严重度，支持 IP/端口数组，按 `hostIp` 优先和 `dstIp` 候选处理资产/目的地址，使用 `devSourceName` 作为来源设备，并把 `traceBackId` 纳入现有证据引用链。

转换链保持为：真实响应 → 现有 `RawJsonlNormalizer` → `NormalizedAlertRecord` → `AlertRecord`。攻击阶段、平台置信度和 GPT 研判等扩展字段通过现有 `scenario_fields` 保留。跨页结果由稳定 ID 规则去重，重复记录保留字段更完整的一条；缺少稳定 ID、非法时间、非法端口、非法严重度、非法状态和非法列表结构均报告为结构化字段映射错误。

本次新增的夹具和测试均使用不可逆占位值。真实平台官方签名、真实凭据、HTTP 翻页和受控非空调用属于李雨妍、杨嘉琪负责的接线与现场复现范围，本任务不伪造这些运行证据。
