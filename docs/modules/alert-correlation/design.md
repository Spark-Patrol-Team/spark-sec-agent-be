# 告警接入与关联模块设计

## 1. 模块目标

本模块负责将固定 JSONL 告警转换为统一 `AlertRecord`，在可解释的最小规则下关联为 `SecurityEvent`，并将该安全事件自动交给风险研判服务。当前目标是提供一条可重复运行的降级链路：**固定 JSONL → 标准化 → AlertRecord → 15 分钟最小关联 → SecurityEvent → 风险研判**。该模块不替代真实平台的实时告警订阅、鉴权或 API 调用。

## 2. 输入、输出与调用边界

| 项目 | 实际契约 | 说明 |
|---|---|---|
| 固定原始输入 | `tests/fixtures/fixed_alerts/raw_alerts.jsonl` | STA/XDR 来源字段结构的脱敏样例。 |
| 固定标准化输入 | `tests/fixtures/fixed_alerts/normalized_alerts.jsonl` | 满足 `NormalizedAlertRecord` 契约的固定样例。 |
| 接入输出 | `AlertRecord` | 由 `src/sec_agent/platforms/jsonl_sample.py` 提供给 `AlertIngestService`。 |
| 关联输出 | `SecurityEvent` | 包含 `alert_refs`、时间范围、实体、关联依据、压缩前后数量与摘要。 |
| 后续输入 | `RiskTriageService.triage(event, alerts)` | `Orchestrator` 在关联成功后立即调用风险研判。 |

`Orchestrator.start` 负责状态流转，关联模块不直接修改 `EventContext.status`。主流程依次记录 `RECEIVED`、`CORRELATING`、`TRIAGED`，之后再进入调查、决策、审批、Mock 处置和验证阶段。

## 3. 固定样例与真实性边界

| 数据类别 | 固定样例标识 | 使用边界 |
|---|---|---|
| 平台字段派生样例 | `FIX-STA-SQLI-001`、`FIX-XDR-WEBSHELL-001`，`sample_nature=platform_derived` | 字段结构和规则名称基于此前平台验证结论整理，已使用 RFC 5737 文档地址完成脱敏；不等同于实时平台返回。 |
| 合成回归样例 | `FIX-STA-LATERAL-001`，`sample_nature=synthetic_regression` | 用于覆盖横向移动、SMB 和回归场景；必须在日志和展示层保留合成标识。 |
| 真实 OpenAPI/MCP 数据 | 不在本模块实现范围内 | `source="xdr"` 的真实 XDR OpenAPI 鉴权、实时拉取和字段映射尚未接入，不能将本模块表述为真实平台实时读取。 |

仓库不得提交真实平台账号、密码、Token、接入码、Cookie、真实内网地址、原始截图或原始 PCAP。

## 4. 标准化规则

`RawJsonlNormalizer` 位于 `src/sec_agent/platforms/raw_jsonl.py`。当 `JSONL_INPUT_MODE=raw` 时，适配器读取原始 JSONL 并标准化；当输入模式为 `normalized` 时，适配器直接读取标准化 JSONL。两条固定路径对同一条样例应得到一致的标准化业务字段。

| 规则 | 实现口径 |
|---|---|
| 时间 | STA 的 `record_time` 或 XDR 的 `alert_time` 补齐 `Asia/Shanghai` 时区，输出带时区的 `event_time`。 |
| 来源设备 | STA 优先使用 `reporting_device_name`；XDR 优先使用 `source_device_name`；字段缺失时按来源回退。 |
| 受影响资产 | 优先使用 `destination_ip`；仅当目的地址缺失时才回退 `host_ip`。 |
| 通用 XDR 高危 | 默认映射为 `high`，风险种子为 80。 |
| WebShell 专项规则 | `WebShell蚁剑工具文件管理` 且原始 `alert_grade=高危` 时专项映射为 `critical`，`risk_score_seed=95`。该规则不升级其他高危告警。 |
| 样例性质 | 原样保留 `platform_derived` 或 `synthetic_regression`。 |
| 证据引用 | `AlertRecord.evidence_refs` 由标准化字段生成；原始输入路径的 `raw_record_ref` 指向 `raw_alerts.jsonl#<sample_id>`。 |

## 5. 最小关联规则

`AlertCorrelationService` 位于 `src/sec_agent/services/correlation.py`。它只处理上层已选定为同一候选攻击活动的告警列表，不承担跨资产攻击图谱、基于概率的聚类或实时流式窗口管理。

同一次关联必须同时满足以下条件：事件类型一致、受影响资产一致、来源设备一致，且第一条与最后一条告警的时间跨度不超过 15 分钟。满足条件的多条告警压缩为一个 `SecurityEvent`；输出 `alert_count_before`、`event_count_after=1`、`entities`、`correlation_reason` 和 `summary`。任何一个条件不满足时抛出可读异常，由上层拆分为不同安全事件，避免将无关告警错误合并。

## 6. 风险研判衔接

关联成功后，`Orchestrator` 将 `SecurityEvent` 写入 `EventContext.event_summary`，再调用 `RiskTriageService.triage(event, alerts)`。对固定 WebShell 样例，风险种子 95 被传递到风险研判，主链进入 `TRIAGED` 后继续完成调查和决策，并因高风险处置停在 `APPROVAL_REQUIRED`。Mock 审批通过后可进入执行和验证，最终达到 `COMPLETED`。

## 7. 异常处理

| 异常类别 | 实际处理 |
|---|---|
| 空告警列表 | `correlate([])` 抛出“无法关联空告警列表”。 |
| 查询标识冲突 | `sample_id` 与 `xdr_event_id` 同时传入且不一致时拒绝读取。 |
| 样例不存在 | JSONL 适配器抛出“JSONL 样例不存在”。 |
| 事件类型、资产或设备不一致 | 关联服务拒绝合并，并说明由上层拆分安全事件。 |
| 超出 15 分钟窗口 | 关联服务拒绝合并，并说明超出最小关联时间窗口。 |
| JSON/契约错误 | JSONL 适配器或标准化器返回带文件与行号的可读异常。 |

## 8. 非目标

本轮不实现真实 XDR OpenAPI/MCP 客户端、实时消息消费、跨事件聚类、攻击链推理、持久化关联图谱或自动处置决策。后续接入真实平台时应复用 `PlatformAdapter` 与 `AlertRecord` 契约，并将实时接口鉴权、超时、限流、重试与审计单独纳入测试。
