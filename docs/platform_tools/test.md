# 平台工具模块测试说明

## 测试范围

本测试覆盖 JSONL 格式、原始字段到标准字段的映射、标准化契约、AlertRecord 适配和最小下游联调。所有测试仅使用 `tests/fixtures/fixed_alerts/` 下的脱敏样例。

## 测试用例

| 测试 ID | 输入 | 操作 | 预期结果 |
|---|---|---|---|
| PT-01 | `raw_alerts.jsonl` | 校验每行 JSON 格式。 | 3 条记录均可解析。 |
| PT-02 | SQL 注入原始样例 | 按映射表标准化。 | `event_type=sql_injection`、`severity=high`、`source_device_name=STA_001`、`affected_asset=198.51.100.20`。 |
| PT-03 | WebShell 原始样例 | 按映射表标准化。 | `event_type=webshell`、`severity=critical`、`risk_score_seed=95`、`source_device_name=XDR`、`affected_asset=198.51.100.11`。 |
| PT-04 | 删除 `destination_ip` 的 WebShell 变体 | 触发回退规则。 | `affected_asset` 使用脱敏后的 `host_ip` 值。 |
| PT-05 | 横向行为标准化样例 | 校验数据性质。 | 保留 `synthetic_regression`，前端和日志能够标识测试性质。 |
| PT-06 | 三条标准化样例 | 校验 JSON Schema。 | 全部满足 `normalized_alert_schema.json`。 |
| PT-07 | 三条标准化样例 | 转换为仓库实际 `AlertRecord`。 | 三条记录均进入主链且关键字段不丢失。 |
| PT-08 | 适配后的 AlertRecord | 调用最小风险、调查、处置和前端流程。 | 每条均产出风险结果、调查提示、处置建议和可展示状态。 |
| PT-09 | `raw_alerts.jsonl` 与 `normalized_alerts.jsonl` | 逐条读取原始样例并标准化，对比固定标准化契约。 | 3 条输出逐字段一致；原始路径 `raw_record_ref` 指向 `raw_alerts.jsonl`。 |
| PT-10 | 同一 WebShell 活动的两条重复 AlertRecord | 在 15 分钟窗口内执行简单关联。 | 压缩为 1 个 SecurityEvent；`alert_count_before=2`、`event_count_after=1`，关联依据包含事件类型、资产、设备和时间窗口。 |
| PT-11 | `destination_ip` 缺失的 XDR 变体 | 执行原始告警标准化。 | `destination_ip` 与 `affected_asset` 仅在目的地址缺失时使用 `host_ip`；通用 WebShell 高危仍为 `high/80`，不触发蚁剑专项覆盖。 |
| PT-12 | `raw` 输入模式的 WebShell 样例 | 运行最小主链并批准 Mock 处置。 | 依次到达 `APPROVAL_REQUIRED` 与 `COMPLETED`，且风险分保持 95。 |

## 回归基线

| 样例 | 预期事件分类 | 预期严重性 | 预期受影响资产 | 必须断言 |
|---|---|---|---|---|
| `FIX-STA-SQLI-001` | `sql_injection` | `high` | `198.51.100.20` | `source_device_name=STA_001`。 |
| `FIX-XDR-WEBSHELL-001` | `webshell` | `critical` | `198.51.100.11` | `risk_score_seed=95`；目的地址优先，不能被 `host_ip` 覆盖。 |
| `FIX-STA-LATERAL-001` | `lateral_movement` | `medium` | `198.51.100.120` | 必须保留 `synthetic_regression`。 |

## 已知边界

样例时间、规则名称和字段结构基于平台验证结论整理，但所有地址已使用 RFC 5737 文档保留地址完成脱敏。`raw` 输入模式验证的是“原始样例→标准化→AlertRecord→最小主链”的可重复降级路径；它不代表实时 XDR 事件聚合、真实平台 API 调用或真实处置执行结果。实时平台路径仍须由可用的 OpenAPI/MCP 接入实现单独验证。
