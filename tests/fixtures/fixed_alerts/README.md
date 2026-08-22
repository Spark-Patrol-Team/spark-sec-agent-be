# 固定告警测试夹具

本目录提供脱敏固定告警输入，用于真实 STA/XDR 平台暂时不可访问、数据波动或模块需要独立开发时的解析器开发、模块联调和回归测试。目录中不包含账号、Token、接入码、真实内网地址、原始平台截图或原始 PCAP 内容。

| 文件 | 用途 |
|---|---|
| `raw_alerts.jsonl` | 原始输入形态样例，供平台接入适配器和解析器测试。 |
| `normalized_alerts.jsonl` | 统一标准事件样例，供风险研判、深度调查、处置闭环和前端直接消费。 |
| `raw_to_normalized_mapping.csv` | 原始字段到标准字段的映射、回退规则与缺失处理。 |
| `normalized_alert_schema.json` | 标准化事件的 JSON Schema，用于契约校验。 |
| `fixture_index.csv` | 样例场景、预期分类、严重性和测试用途索引。 |

## 数据性质

`platform_derived` 表示字段结构基于已验证平台数据整理且已完成脱敏；`synthetic_regression` 表示脱敏合成回归样例，仅用于测试。所有地址均使用 RFC 5737 文档保留地址。各模块必须保留并展示 `sample_nature`，不得将合成样例表述为实时平台告警。

## 消费规则

`affected_asset` **优先使用 `destination_ip`**；仅当 `destination_ip` 缺失时，适配器才可使用原始 `host_ip` 回退。XDR 原始告警“高危”默认映射为 `severity: "high"`；但 `WebShell蚁剑工具文件管理` 高危固定样例按专项规则映射为 `severity: "critical"`，且 `risk_score_seed` 为 `95`。STA 样例从 `reporting_device_name` 获取 `source_device_name`，XDR 样例从 `source_device_name` 获取；仅在字段缺失时按来源类型回退。
