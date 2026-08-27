# 平台工具模块设计

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 模块名称 | 平台工具（`platform-tools`） |
| 本轮任务 | `T0827-06`：真实 XDR 输入契约与适配准备 |
| 负责人 | 陈敏 |
| 适用分支基线 | `main@4190550` |
| 状态 | 已完成字段映射、脱敏结构样例、分页/错误规则和最小契约测试；真实 XDR OpenAPI 适配器待接口资料确认后实施。 |
| 关联材料 | `xdr_input_contract.md`、`xdr_field_mapping.csv`、`tests/fixtures/xdr_contract/` |

## 2. 模块职责

平台工具模块负责将平台能力封装为稳定、可审计的内部输入输出边界，为告警接入、关联、风险研判、深度调查和处置闭环提供统一接口。本轮聚焦真实 XDR 告警输入的**适配准备**：明确真实 XDR 事件怎样在适配层被转换为现有 `NormalizedAlertRecord` 与 `AlertRecord`，而不让业务 service 直接依赖厂商 SDK、HTTP 地址或认证细节。

当前仓库已经支持 `fixed_sample` 与 `jsonl_sample` 两种离线输入；`PlatformAdapter.fetch_alerts(sample_id, xdr_event_id)` 已给出统一读取签名，但 `source="xdr"` 的真实读取路径仍抛出 `NotImplementedError`，容器层也尚未注册 `xdr_openapi` 后端。本轮不修改该边界，不将准备材料表述为真实 XDR 已接入。

## 3. 设计目标与范围

本轮目标是建立可供下一轮实现和验收的最小契约：稳定事件标识、发生时间、告警名称、事件类型、严重性、源/目的实体、资产、来源设备、证据引用、分页与错误处理必须有明确的映射或缺失规则。真实接入必须只替换输入来源，保持固定 JSONL 降级路径、`AlertRecord` 契约、15 分钟关联逻辑和既有回归结果不变。

本轮不包含具体 XDR URL、请求方法、认证头、Token、Cookie、真实事件/告警/资产 ID、真实 IP、用户名、原始响应、真实截图或真实 MCP 调用。这些只能在本地受控接入环境中出现，不能进入仓库、PR、群聊或测试夹具。

## 4. 输入、输出与调用边界

| 边界 | 输入 | 输出 | 责任 |
|---|---|---|---|
| 真实 XDR 查询（待接入） | 本地受控的时间窗口、运行时实体和认证配置 | 提供方原始响应，仅驻留内存或受控本地文件 | 平台适配层 |
| XDR 适配器（待实现） | XDR 原始记录 | `NormalizedAlertRecord`（可选中间层） | `src/sec_agent/platforms/xdr_openapi.py` |
| 现有 JSONL 适配器 | 固定 JSONL 或 raw→normalized 结果 | `AlertRecord` | `src/sec_agent/platforms/jsonl_sample.py` |
| 告警接入服务 | `PlatformAdapter.fetch_alerts(...)` | `list[AlertRecord]` | `src/sec_agent/services/ingest.py` |
| 关联与研判 | `AlertRecord` | `SecurityEvent`、`TriageResult` | `src/sec_agent/services/correlation.py` 及后续服务 |

真实 XDR 适配器最终必须输出与 `jsonl_sample.py` 相同的 `AlertRecord` 形状：`alert_id`、`source`、`occurred_at`、`name`、`alert_type`、`raw_severity`、`src_ip`、`dst_ip`、端口、资产、`attack_status`、`scenario_fields`、`evidence_refs` 与 `raw_record_ref`。字段细则见 [xdr_input_contract.md](xdr_input_contract.md) 和 [xdr_field_mapping.csv](xdr_field_mapping.csv)。

## 5. 核心映射规则

| 规则 | 设计要求 |
|---|---|
| 唯一标识 | 选用提供方稳定 `event_id`、`alert_id` 或等价 ID，用于跨页去重；不得用列表序号代替。 |
| 时间 | 事件时间必须可解析并带时区；无时区时仅可按接入日确认的提供方时区补齐。 |
| 目的资产 | `destination_ip` 优先；仅当其缺失时才回退 `host_ip`。两者皆缺失时显式记录资产缺口。 |
| 来源设备 | XDR 优先 `source_device_name`，再回退 `data_source`，最终为 `XDR`；不得套用 STA 的设备映射规则。 |
| 严重性 | 通用规则为 `严重→critical`、`高危→high`、`中危→medium`、`低危→low`。`WebShell蚁剑工具文件管理 + 高危→critical/95` 仅是固定样例的专项规则，不推广为所有 XDR 高危告警。 |
| 事件类型 | 通过受控词典标准化为 `sql_injection`、`webshell`、`lateral_movement`、`unauthorized_access` 或 `other`；未知类别保留原始值并映射为 `other`。 |
| 证据引用 | 必须形成不含凭据的内部证据引用与受控 `raw_record_ref`；禁止将详情 URL、Token 或原始响应写入日志和仓库。 |

## 6. 分页、去重与错误语义

适配器应使用一次固定的含时区时间窗口完成查询；实际平台确定页码或游标分页后只能选择一种方式，不得混用。跨页重复记录按稳定提供方 ID 去重，同一 ID 保留时间更完整、证据更多的记录，并保留去重数量用于审计。

传输、认证、平台错误与业务零命中必须分别表达。认证失败不重试；网络超时只对只读请求进行有限重试；请求成功但记录列表为空应记为 `success + zero_records`，不能说成连接失败，也不能伪造事件。固定 JSONL 中的 RFC 5737 地址不应作为真实 XDR 或 MCP 查询实体，使用该类样例查询真实数据源而零命中属于预期边界。

## 7. 脱敏与审计边界

真实事件实体只允许在进程内存、平台审计系统、受控本地 `.env` 或已忽略的 `*.local.json` 中存在。可提交的请求/响应结构样例仅保留字段角色、语义化占位符、RFC 5737 文档地址和不含真实值的分页/错误语义。调试完成后应清理临时原始响应，不应将其复制进 Git 历史。

所有平台工具调用都应保留 `trace_id`、`idempotency_key`、脱敏参数摘要、`raw_result_ref` 和结构化错误类别。读取类工具的副作用类型为 `read_only`，不得在查询过程中触发真实隔离、阻断、删除或处置动作。

## 8. 与固定样例和真实 MCP 的关系

固定 JSONL 的作用是提供可重复的离线回归，不承担真实平台实体查询职责。其 `platform_derived` 表示字段结构来自已验证平台记录并已脱敏，`synthetic_regression` 表示合成回归场景；两者均不能被描述为实时拉取结果。

深度调查中的真实 MCP 查询应使用同一条真实 XDR 事件在运行时产生的实体和时间窗口。若 MCP 连接成功但业务查询零命中，应形成“无数据/证据不足”记录，并触发人工接管，而不是将空结果当作有效证据。本轮仅固化该上游契约和验收边界，不修改深度调查 Agent 的 MCP 空结果处理代码。

## 9. 验收标准

1. 字段映射表覆盖事件 ID、时间、类型、源/目的地址、资产、设备来源、严重性、证据引用、分页、去重和缺失字段规则。
2. 请求/响应样例可解析，包含结构而不包含真实平台实体或凭据。
3. `tests/test_xdr_input_contract.py` 可验证样例的结构、目的资产规则、来源设备规则和空结果语义。
4. 已有 `fixed_sample` 和 `jsonl_sample` 路径不被改动，既有告警关联回归不受影响。
5. 接入当天可依据本契约完成一次本地只读真实事件验证，并仅记录脱敏结论与字段类型。

## 10. 已知限制与后续事项

真实 XDR OpenAPI 的端点、认证、分页字段、响应 schema、速率限制和权限范围尚未得到可提交的官方接口资料，因此当前无法也不应实现真实读取。下一轮由陈敏提供真实字段存在性和映射确认，由杨嘉琪确认可调用入口、schema、鉴权与只读范围；实现人员据此新增 `xdr_openapi.py` 和容器注册，再执行固定样例回归与一条真实事件的本地受控验证。

## 11. 变更记录

| 日期 | 任务 | 变更 |
|---|---|---|
| 2026-08-27 | `T0827-06` | 补充真实 XDR 输入契约、字段映射、分页/错误规则、脱敏边界和明日接入验收要求。 |
