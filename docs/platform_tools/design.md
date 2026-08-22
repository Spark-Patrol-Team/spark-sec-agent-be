# 平台工具模块设计说明

## 目标与边界

平台工具模块负责将 STA/XDR 原始日志或告警解析为统一事件输入，向风险研判、深度调查、处置闭环和前端模块提供可追溯、可测试的标准化数据。模块不负责执行真实阻断、隔离、删除、回放或平台配置修改。平台侧原始凭据、截图、接入码、真实网络拓扑和原始 PCAP 内容不得进入仓库。

真实平台暂时不可用时，使用 `tests/fixtures/fixed_alerts/` 中的脱敏样例维持开发和联调连续性。所有消费者必须保留 `sample_nature`，以区分平台字段派生样例与合成回归样例。

## 输入与输出

| 输入层 | 格式 | 典型字段 | 输出 |
|---|---|---|---|
| STA 原始日志 | JSON 或日志记录 | `record_time`、`reporting_device`、`reporting_device_name`、`rule_name`、源/目的 IP 与端口 | 标准化安全事件。 |
| XDR 原始告警 | JSON 或告警记录 | `alert_time`、`alert_name`、`alert_grade`、`alert_classification`、`source_ip`、`destination_ip`、`host_ip`、`source_device_name` | 标准化安全事件。 |
| 固定测试样例 | JSONL | 原始样例或标准化样例 | 解析测试、模块联调和前端回归。 |

标准化事件最小字段为 `event_id`、`event_time`、`source_device_type`、`event_type`、`rule_or_event_name`、`severity`、`source_ip`、`destination_ip`、`affected_asset`、`evidence_source`、`sample_nature` 和 `status`。可选的 `source_device_name` 用于展示、路由和日志归因。

## 已确认业务规则

| 规则 | 必须遵循的行为 |
|---|---|
| 受影响资产优先级 | `affected_asset` 优先使用 `destination_ip`；仅当 `destination_ip` 缺失时，才使用 `host_ip` 回退。 |
| XDR 基础严重性 | `Critical` 映射为 `critical`，`High` 映射为 `high`，`Medium` 映射为 `medium`，`Low` 映射为 `low`。 |
| WebShell 固定样例覆盖规则 | `WebShell蚁剑工具文件管理` 且原始等级为高危时，标准化为 `severity=critical`，并使用 `risk_score_seed=95`。 |
| 设备名称 | STA 优先使用 `reporting_device_name`；XDR 优先使用 `source_device_name`；缺失时按来源类型回退。 |
| 证据可追溯性 | 保留 `evidence_source` 与 `evidence_refs`，用于下游解释和证据追溯。 |

## 安全边界

所有样例地址均使用 RFC 5737 文档保留地址。仓库中不得提交原始平台截图、真实内网 IP、账号、密码、Cookie、Token、接入码、原始 PCAP 或未脱敏的平台返回内容。
