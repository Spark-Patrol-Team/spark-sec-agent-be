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

## 当前代码入口

- 标准化 JSONL 契约模型：`src/sec_agent/domain/models.py` 中的 `NormalizedAlertRecord`。
- 原始 JSONL 标准化器：`src/sec_agent/platforms/raw_jsonl.py` 中的 `RawJsonlNormalizer`，负责 STA/XDR 原始字段映射、Asia/Shanghai 时间补齐、证据引用、严重性专项规则和资产回退。
- JSONL 平台适配器：`src/sec_agent/platforms/jsonl_sample.py`。`input_mode=normalized` 直接读取 `normalized_alerts.jsonl`；`input_mode=raw` 读取 `raw_alerts.jsonl` 并调用标准化器，之后统一转换为 `AlertRecord`。
- 平台后端装配：`src/sec_agent/bootstrap/container.py`，通过 `PLATFORM_BACKEND=jsonl_sample` 启用，并用 `JSONL_INPUT_MODE=normalized|raw` 显式选择输入路径。
- 主链接入点：`src/sec_agent/services/ingest.py` 只负责调用平台适配器；字段解析保留在 `platforms/`，不在编排层重复实现。
- 简单关联服务：`src/sec_agent/services/correlation.py`。同一主链候选告警要求事件类型、受影响资产、来源设备一致，且时间跨度不超过 15 分钟；服务输出关联依据、时间范围、实体、压缩前数量和关联后事件数。
- 风险研判接入：`src/sec_agent/services/triage.py` 会使用 `severity` 和 `risk_score_seed`，确保标准化样例中的确认分值不被主链降级。

## 本地联调方式

```bash
# 直接读取已标准化样例
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample JSONL_INPUT_MODE=normalized \
PYTHONPATH=src python -m sec_agent.scripts.run_flow

# 读取 raw_alerts.jsonl，并在接入层完成标准化后进入相同主链
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample JSONL_INPUT_MODE=raw \
PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

如需指定接口调用样例，`source` 使用 `jsonl_sample`，`sample_id` 使用 `normalized_alerts.jsonl` 或 `raw_alerts.jsonl` 中的 `event_id/sample_id`，例如 `FIX-XDR-WEBSHELL-001`。原始输入路径会将 `raw_record_ref` 定位为 `jsonl://fixed_alerts/raw_alerts.jsonl#<sample_id>`，以保留原始证据引用。

## 最小验收条件

三条固定样例均应能从 `normalized` 与 `raw` 两条输入路径进入 `AlertRecord`，且标准化结果一致。SQL 注入样例必须保持 `severity=high`、`source_device_name=STA_001` 和 `affected_asset=198.51.100.20`。WebShell 样例必须保持 `severity=critical`、`risk_score_seed=95`、`source_device_name=XDR` 和 `affected_asset=198.51.100.11`。同一 WebShell 活动的重复告警必须在 15 分钟窗口内压缩为 1 个 `SecurityEvent`，并输出明确关联依据。解析、映射、字段或枚举不兼容时必须返回可读错误，不得静默丢弃记录。
