# 平台工具模块开发与 AlertRecord 对接说明

## 仓库落位

固定样例放入 `tests/fixtures/fixed_alerts/`，模块文档放入 `docs/platform_tools/`。仓库采用 `src/sec_agent/` 的 Python 分层结构：`domain/` 维护核心业务模型，`platforms/` 维护来源平台适配，`services/` 维护流程编排。

| 标准化字段 | AlertRecord 应承载的业务语义 | 陈敏确认的来源与规则 | 代码适配职责 |
|---|---|---|---|
| `event_id` | 告警/记录唯一标识 | 固定样例 ID 或平台事件 ID。 | 对应仓库唯一 ID 字段并保证去重。 |
| `event_time` | 发生时间 | `record_time` 或 `alert_time` 规范化为 ISO-8601。 | 校验并映射到模型时间字段。 |
| `source_device_type` | 数据来源设备类型 | STA、XDR 等。 | 映射到来源/产品类型字段。 |
| `source_device_name` | 来源设备名称 | STA 取 `reporting_device_name`；XDR 取 `source_device_name`；缺失时回退。 | 映射到设备名称字段或来源元数据。 |
| `event_type` | 统一事件分类 | SQL 注入、WebShell、横向移动等。 | 映射到告警类别/场景字段。 |
| `rule_or_event_name` | 原始规则或告警名称 | 原文保留。 | 映射到标题/规则名称字段。 |
| `severity` | 初始严重性 | XDR 高危默认映射为 `high`；`WebShell蚁剑工具文件管理` 高危固定样例映射为 `critical`。 | 使用仓库风险等级枚举；WebShell 固定样例必须保留 `critical`。 |
| `source_ip` / `destination_ip` | 网络端点 | 已脱敏来源字段。 | 映射到源/目的资产字段。 |
| `affected_asset` | 处置或调查优先资产 | **优先 `destination_ip`，仅 destination 缺失时回退 `host_ip`。** | 不得反向使用 `host_ip` 作为优先值。 |
| `evidence_source` / `evidence_refs` | 证据来源与字段引用 | 标识 XDR 日志、XDR 告警或固定回归样例。 | 放入证据或元数据字段。 |
| `sample_nature` | 数据性质标识 | `platform_derived` 或 `synthetic_regression`。 | 用于 UI、日志或测试标识，不得丢弃。 |
| `status` | 初始流程状态 | 固定样例均为 `new`。 | 映射到流程状态。 |

## 适配流程

1. 逐行读取 `raw_alerts.jsonl`，使用 `raw_to_normalized_mapping.csv` 完成标准化；
2. 使用 `normalized_alert_schema.json` 校验标准化对象；
3. 将标准化对象转换为 `src/sec_agent/domain/` 中的实际 `AlertRecord`；
4. 以 `event_id` 对齐 `normalized_alerts.jsonl`，对关键字段进行断言；
5. 将转换后的 `AlertRecord` 投入现有风险、调查、处置和前端流程；
6. 保留 `sample_nature=synthetic_regression`，避免合成样例混入真实平台展示数据。

## 最小验收条件

三条固定样例均应能进入 `AlertRecord`。SQL 注入样例必须保持 `severity=high`、`source_device_name=STA_001` 和 `affected_asset=198.51.100.20`。WebShell 样例必须保持 `severity=critical`、`risk_score_seed=95`、`source_device_name=XDR` 和 `affected_asset=198.51.100.11`。解析、映射、字段或枚举不兼容时必须返回可读错误，不得静默丢弃记录。
