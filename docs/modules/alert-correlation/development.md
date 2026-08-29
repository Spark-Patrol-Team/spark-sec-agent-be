# 告警接入与关联模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联） |
| 负责人 | 陈敏 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 + 固定 JSONL fallback + Mock 主链；真实 XDR/MCP 未接入。 |
| 关联任务/需求 | `T0826-06`｜固定 JSONL 告警接入关联回归与文档补齐。 |
| 关联正式交付章节 | `docs/deliverables/system-development-and-operation-guide.md`：第 8 章主流程说明、第 9 章模块说明与接入位置、第 11 章测试与验证。 |
| 对应 PR 或 Commit | PR #17；`1a5bbf1`（后续模板对齐提交追加至同一 PR）。 |
| 适用代码版本 | `main@95defad` 加 PR #17 内容（隔离工作区重放并联调）。 |
| 最后更新时间 | 2026-08-26 |

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
