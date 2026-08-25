# 告警接入与关联模块测试说明

## 1. 测试目标

本模块测试固定 JSONL 的告警读取、标准化、严重性/资产映射、证据引用、最小关联和 `SecurityEvent` 到风险研判的自动衔接。测试仅使用仓库 `tests/fixtures/fixed_alerts/` 中的脱敏样例，不调用真实 XDR OpenAPI、MCP 或真实处置接口。

## 2. 测试位置与命令

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_alert_correlation_regression.py` | T0826-06：固定样例基线、证据引用、15 分钟窗口、异常输入、自动风险研判。 |
| `tests/test_raw_jsonl_ingest_and_correlation.py` | raw 与 normalized 一致性、资产回退、重复压缩、原始输入主链。 |
| `tests/test_jsonl_platform.py` | JSONL 平台适配、证据查询、Mock 处置验证和审批主链。 |

```bash
PYTHONPATH=src python -m unittest tests.test_alert_correlation_regression
PYTHONPATH=src python -m unittest \
  tests.test_alert_correlation_regression \
  tests.test_raw_jsonl_ingest_and_correlation \
  tests.test_jsonl_platform
PYTHONPATH=src python -m unittest discover -s tests
```

## 3. 回归用例

| 用例 ID | 输入与操作 | 预期结果 |
|---|---|---|
| AC-01 | 读取 3 条 `normalized_alerts.jsonl` 固定样例。 | SQL 注入为 `high`、资产 `198.51.100.20`、设备 `STA_001`；WebShell 为 `critical/95`、资产 `198.51.100.11`、设备 `XDR`；横向移动保留 `synthetic_regression`。 |
| AC-02 | `JSONL_INPUT_MODE=raw` 读取 WebShell 样例。 | 原始记录引用为 `jsonl://fixed_alerts/raw_alerts.jsonl#FIX-XDR-WEBSHELL-001`；证据字段包含 `alert_name` 与 `alert_grade`。 |
| AC-03 | 对单条 WebShell AlertRecord 关联。 | 输出一个 SecurityEvent，保留告警引用、资产 `198.51.100.11`、设备 `XDR` 和事件类型关联依据。 |
| AC-04 | 将同一 WebShell 告警复制为相隔恰好 15 分钟的两条记录后关联。 | 允许合并，`alert_count_before=2`、`event_count_after=1`。 |
| AC-05 | 将同一 WebShell 告警复制为相隔 15 分 1 秒的两条记录后关联。 | 拒绝合并，异常说明超出最小关联时间窗口。 |
| AC-06 | 对空列表、冲突的 `sample_id/xdr_event_id` 执行关联或读取。 | 返回可读异常；不得产生空 SecurityEvent 或静默读取错误样例。 |
| AC-07 | 以 raw WebShell 样例调用 `Orchestrator.start`。 | `EventContext.event_summary` 存在，时间线包含 `TRIAGED`，风险分为 95，主链因高风险处置到达 `APPROVAL_REQUIRED`。 |
| AC-08 | 对 AC-07 结果批准 Mock 处置。 | 后续状态到达 `EXECUTING`、`VERIFYING`、`COMPLETED`，验证引用由 Mock 平台返回。 |

## 4. 断言口径

关联成功并不表示真实攻击已经被外部平台确认，只表示固定输入在当前 MVP 规则下满足关联条件。`SecurityEvent.alert_refs` 用于保留告警级可追溯性，`correlation_reason` 用于展示类型、资产、设备和时间窗口依据；字段级证据由 `AlertRecord.evidence_refs` 与适配器的 `evidence_lookup` 提供。

以下情况必须拒绝合并：事件类型不同、目标资产不同、来源设备不同、告警时间跨度超过 15 分钟。拒绝时应保留可读错误，供上层拆分事件或人工排查，不能为了提高“关联率”而合并无关记录。

## 5. 本轮实际执行结果

本轮在最新 `main` 的隔离工作区中完成复测。执行 `tests.test_alert_correlation_regression`、`tests.test_raw_jsonl_ingest_and_correlation` 和 `tests.test_jsonl_platform` 共运行 17 项测试，全部通过。执行 `python -m unittest discover -s tests` 共运行 70 项测试，结果为 `OK (skipped=1)`；跳过项与未配置真实深信服 MCP 地址有关，不影响固定 JSONL、标准化、关联或 Mock 主链结果。

使用 `PLATFORM_BACKEND=jsonl_sample`、`JSONL_INPUT_MODE=raw` 的主流程实测依次出现 `RECEIVED`、`CORRELATING`、`TRIAGED`、`INVESTIGATING`、`DECISION_READY`、`APPROVAL_REQUIRED`。Mock 审批后继续出现 `EXECUTING`、`VERIFYING` 和 `COMPLETED`。这证明生成的 `SecurityEvent` 已实际进入风险研判和后续 MVP 主链；它不证明真实平台或真实处置动作已被调用。

## 6. 数据边界

`platform_derived` 是基于已验证平台字段结构的脱敏固定样例，不是运行时实时拉取数据；`synthetic_regression` 是人为构造的回归输入。真实 XDR OpenAPI/MCP 仍未接入，因此本测试不覆盖真实鉴权、网络错误、接口分页、限流、重试或平台返回的动态字段。
