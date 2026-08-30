# 告警接入与关联模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | 真实字段确认|
| 负责人 | 陈敏 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 + 固定 JSONL fallback + Mock 主链；不含真实平台实时接入。 |
| 关联任务/需求 | `T0828-06` |
| 关联正式交付章节 | `docs/deliverables/安全智能体系统设计说明书V2.md`：模块设计、统一事件上下文、主流程与状态流转、平台接入边界。 |
| 对应 PR/Commit | PR #17；`1a5bbf1`（后续文档模板对齐提交追加到同一 PR）。 |
| 最后更新时间 | 2026-08-30 |
| 最后复验时间 | 2026-08-30。 |

## 1. 目标与非目标

### 1.1 目标

- 读取脱敏固定 JSONL 告警，并在 `raw` 或 `normalized` 输入模式下转换为统一 `AlertRecord`。
- 按固定样例契约复验严重性、受影响资产、来源设备和证据引用映射。
- 将同一候选攻击活动在 15 分钟窗口内关联为一个 `SecurityEvent`，保留参与告警、实体、关联依据和压缩前后数量。
- 使 `SecurityEvent` 自动进入 `RiskTriageService`，由编排层继续推进 MVP 主链。

### 1.2 非目标

- 不实现真实 XDR OpenAPI/MCP 鉴权、实时告警拉取、分页、限流或网络重试。
- 不实现跨资产、跨设备、跨场景的攻击图谱、概率聚类或长期窗口聚合。
- 不直接决定或执行真实处置动作，不绕过审批或编排状态机。

## 2. 职责与边界

- 本模块负责：固定 JSONL 接入、原始字段标准化、最小关联、关联异常拒绝、告警与证据引用保留，以及为风险研判提供 `SecurityEvent`。
- 本模块不负责：真实平台客户端、风险评分规则本身、调查 Agent 的工具编排、处置动作和最终前端展示。
- 需要人工参与的环节：真实 XDR/MCP 接入前的接口资料确认；超过关联边界、证据不足或真实平台异常时的事件拆分与人工判断。

## 3. 输入与输出

### 3.1 输入

| 字段/对象 | 类型 | 必填 | 来源 | 含义与约束 |
|---|---|---|---|---|
| `raw_alerts.jsonl` | JSONL 文件 | raw 模式必填 | `tests/fixtures/fixed_alerts/` | STA/XDR 字段结构的脱敏固定样例。 |
| `normalized_alerts.jsonl` | JSONL 文件 | normalized 模式必填 | `tests/fixtures/fixed_alerts/` | 满足 `NormalizedAlertRecord` 契约的固定样例。 |
| `AlertRecord` 列表 | `list[AlertRecord]` | 是 | `JsonlSampleAdapter` / `AlertIngestService` | 必须属于同一候选攻击活动后才可输入关联。 |
| `JSONL_INPUT_MODE` | `normalized` / `raw` | 否 | 配置 | `normalized` 直接读取标准化样例；`raw` 先标准化后适配。 |

### 3.2 输出

| 字段/对象 | 类型 | 去向 | 含义与约束 |
|---|---|---|---|
| `AlertRecord` | `AlertRecord` | `AlertIngestService`、`Orchestrator` | 保留告警 ID、时间、类型、严重性、资产、样例性质、字段级证据和原始记录引用。 |
| `SecurityEvent` | `SecurityEvent` | `EventContext.event_summary`、`RiskTriageService` | 包含 `alert_refs`、时间范围、实体、`correlation_reason`、`alert_count_before`、`event_count_after` 和摘要。 |
| 关联异常 | `ValueError` | `Orchestrator` 错误处理与上层拆分逻辑 | 空输入、事件类型/资产/设备不一致或超过 15 分钟窗口时拒绝合并。 |

## 4. 核心流程与状态变化

1. `JsonlSampleAdapter` 按输入模式读取固定 JSONL；raw 模式调用 `RawJsonlNormalizer`，normalized 模式校验 `NormalizedAlertRecord`。
2. 适配器生成 `AlertRecord`，写入 `source_device_name`、`affected_asset`、`sample_nature`、`risk_score_seed`、`evidence_refs` 与 `raw_record_ref`。
3. `AlertIngestService` 将告警交给 `Orchestrator`；编排器记录 `RECEIVED` 后进入 `CORRELATING`。
4. `AlertCorrelationService` 校验事件类型、目标资产、来源设备和 15 分钟窗口，生成 `SecurityEvent` 并写入 `EventContext.event_summary`。
5. 编排器调用 `RiskTriageService.triage(event, alerts)`，记录 `TRIAGED`；后续调查、决策、审批、Mock 处置和验证仍由其他模块及编排器处理。
6. 关联条件不满足或接入失败时，模块返回可读异常；编排器记录错误并转入相应失败/人工路径，不产生伪造的关联事件。

关联模块不直接修改 `EventContext.status`；所有状态变化仅由 `src/sec_agent/services/orchestrator.py` 与状态机推进。

## 5. 上下游关系与契约

| 方向 | 模块/接口 | 契约或文档位置 | 当前状态 |
|---|---|---|---|
| 上游 | JSONL 固定样例 | `tests/fixtures/fixed_alerts/`、`NormalizedAlertRecord` | 已对齐。 |
| 上游 | 平台适配器 | `src/sec_agent/platforms/jsonl_sample.py`、`raw_jsonl.py` | 已对齐，仅固定样例模式。 |
| 当前模块 | 关联服务 | `src/sec_agent/services/correlation.py` | 已对齐，最小 15 分钟规则。 |
| 下游 | 风险研判 | `src/sec_agent/services/triage.py`、`RiskTriageService.triage(event, alerts)` | 已对齐，WebShell 固定样例风险种子为 95。 |
| 下游 | 主链编排 | `src/sec_agent/services/orchestrator.py`、`EventContext` | 已对齐。 |
| 后续 | 调查/处置/前端 | `EventContext.event_summary`、`triage`、`investigation`、`response` | 已对齐，具体业务由对应模块负责。 |

## 6. 安全边界

- 权限与审批：关联模块不执行外部动作；高风险处置由后续响应模块触发审批。
- 输入校验：空列表、标识冲突、样例不存在、类型/资产/设备冲突和窗口超时均拒绝并返回可读错误。
- 敏感信息处理：仅提交 RFC 5737 文档地址和脱敏固定样例；真实账号、密码、Token、接入码、Cookie、真实内网地址、截图和原始 PCAP 不入仓库。
- 失败、超时与人工接管：当前实现只校验固定样例关联时间窗口；真实平台的网络超时、重试、回滚和人工接管策略尚未实现。
- 真实执行与 Mock 边界：本模块输出固定 JSONL fallback 数据；Mock 处置流程可运行，但不代表真实平台动作已执行。

## 7. 关键设计决策

| 决策 | 原因 | 未采用方案及原因 |
|---|---|---|
| 使用 `AlertRecord` 作为关联输入 | 已是主链接入后的统一对象，可避免下游重复解析平台 JSON。 | 直接在关联服务解析原始 STA/XDR JSON 会破坏平台适配边界。 |
| 采用“类型 + 资产 + 设备 + 15 分钟”最小规则 | 可解释、易回归，适合 MVP 固定样例演示。 | 概率聚类和攻击图谱缺少稳定标签、实时流和评估数据，当前不实现。 |
| `destination_ip` 优先、`host_ip` 回退 | 与已合入样例、映射表和处置目标语义一致。 | `host_ip` 全局优先会与固定样例契约冲突。 |
| WebShell 蚁剑专项 `critical/95` | 保持已确认的固定样例基线，并保证风险研判高风险路径可复现。 | 将所有 XDR 高危升级为 critical 会夸大通用告警风险。 |
| 证据只保存引用 | 避免在统一上下文中复制原始平台大对象与敏感数据。 | 直接保存原始响应会增加敏感信息和存储边界风险。 |

## 8. 非功能、可观测与审计要求

| 维度 | 当前要求或设计 | 验证方式 |
|---|---|---|
| 性能与时延 | 固定 JSONL 小规模回归，无真实吞吐量 SLA。 | 单元测试和本地主流程运行；不宣称生产性能指标。 |
| 稳定性与可重复性 | 相同固定输入应产生一致字段、风险基线和关联数量。 | `tests/test_alert_correlation_regression.py` 与既有 JSONL 回归。 |
| 可观测性 | `EventContext.timeline` 记录 `RECEIVED`、`CORRELATING`、`TRIAGED` 等状态；错误写入 `errors`。 | 主流程脚本输出与事件上下文。 |
| 审计与追踪 | 使用 `alert_refs`、`raw_record_ref`、字段级 `evidence_refs`、`trace_id` 和 `event_id` 追溯。 | 固定样例测试与 `evidence_lookup`。 |

## 9. 当前限制与后续事项

| 限制或未实现项 | 对主链影响 | 后续条件/负责人 |
|---|---|---|
| 真实 XDR OpenAPI/MCP 未接入 | 不阻塞固定 JSONL MVP 主链；阻塞真实平台实时演示。 | 平台接口文档、鉴权方式与脱敏响应样例确认后，由平台适配器负责人实现。 |
| 跨资产/跨设备攻击图谱未实现 | 不阻塞当前单候选活动关联；限制复杂攻击链分析。 | 获得稳定事件标签、数据量与评估口径后扩展。 |
| 真实平台超时、限流、重试未实现 | 不影响固定样例；影响真实接入可靠性。 | 真实客户端接入时补充并测试。 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-25 | PR #17 / `1a5bbf1` | 新增固定 JSONL 告警接入关联专项回归与设计文档。 | 是，隔离环境专项 17 项和全量 70 项测试已执行。 |
| 2026-08-25 | PR #17 后续提交 | 对齐团队统一模块文档模板，补充文档信息、契约、证据、限制和变更记录。 | 文档事实与同一代码基线复核。 |
| 2026-08-26 | PR #17 后续联调提交 | 在最新 `main@95defad` 上重放 PR #17 内容，复测固定 JSONL、关联和风险研判衔接。 | 是，专项 17 项、全量 79 项测试均通过，框架 skipped 1；raw 主链到 `COMPLETED`。 |
| 2026-08-27 | PR #22 / `5ea5a53` | 在不改动上述 8 月 25—26 日历史内容和变更记录的前提下，新增真实 XDR 输入契约、字段映射、脱敏结构样例及接入前验收口径。 | 是，脱敏契约测试 4 项通过；既有 JSONL/关联回归 17 项通过。 |
| 2026-08-30 | PR #34  | 新增真实 XDR 字段映射与输入质量补充。 | 是，脱敏契约测试 4 项通过；既有 JSONL/关联回归 17 项通过。 |

## 11. T0827-06 补充：真实 XDR 输入契约与告警关联链路衔接

本节是对上述 `alert-correlation` 设计的**追加说明**，不替换其固定 JSONL、标准化、最小关联、风险研判或 Mock 主链的既有设计结论。为保持“一项任务一个 PR”的协作边界，本补充及其配套文件位于 PR #22 的 `docs/modules/platform-tools/`；其技术基础是已经合入 `main@4190550` 的 PR #17 下游告警接入与关联实现，而非对 PR #17 的回写或改动。

### 11.1 本轮目标、非目标与实现状态

本轮目标是为下一轮真实 XDR 的**只读输入接入**准备可审查的字段映射、无真实值结构样例、错误与零记录语义以及最小验收口径。真实接入完成后只能替换“读取告警”的上游来源；`AlertRecord`、`SecurityEvent`、15 分钟最小关联、`RiskTriageService`、编排状态推进和固定 JSONL fallback 均应保持兼容。

本轮不实现 `src/sec_agent/platforms/xdr_openapi.py`，不注册 `PLATFORM_BACKEND=xdr_openapi`，不调用真实 XDR OpenAPI/MCP，也不保存或猜测真实端点、认证方式、分页字段、请求参数或响应值。当前 `AlertIngestService.ingest(source="xdr", ...)` 仍明确属于未实现路径，因此本节不能作为“真实 XDR 已接入”的依据。

### 11.2 输入契约与下游对象的对应关系

| 真实 XDR 的字段角色 | 标准化与主链目标 | 本轮约束 | 与既有设计的关系 |
|---|---|---|---|
| 稳定事件/告警标识 | `NormalizedAlertRecord.event_id`、`AlertRecord.alert_id` | 接入日从提供方确认稳定 ID；不得使用列表序号。缺失时拒绝该记录并仅记录脱敏错误原因。 | 保证 `alert_refs`、跨页去重和后续事件审计可追溯。 |
| 发生时间 | `event_time`、`occurred_at` | 必须可解析并包含时区；无时区时仅按接入日确认的提供方时区补齐。 | 保证既有 15 分钟窗口的输入语义一致。 |
| 告警名称、分类与严重性 | `name`、`alert_type`、`raw_severity` 与风险输入 | 名称和严重性为最小必填；分类经受控词典映射。真实枚举未确认前不猜测。 | 保持统一 `AlertRecord`，避免在关联服务中解析平台原始 JSON。 |
| 源/目的实体与资产 | `src_ip`、`dst_ip`、`affected_asset`、`assets` | 始终优先 `destination_ip`；只有其缺失时才回退 `host_ip`。两者均无时显式保留资产缺口，不虚构默认资产。 | 延续第 7 节的既有关键设计决策。 |
| 来源设备 | `scenario_fields.source_device_name` | XDR 优先 `source_device_name`，缺失才回退 `data_source`，最终回退 `XDR`。不得使用 STA 的 `reporting_device_name`。 | 保证同来源设备这一关联条件可解释；不改变 STA 的独立规则。 |
| 证据与原始引用 | `evidence_refs`、`raw_record_ref` | 只保存匿名内部引用或受控本地审计引用；不提交真实详情 URL、认证头、Token 或原始响应。 | 延续第 6 节的证据最小化和隐私边界。 |

完整字段级映射见 [xdr_field_mapping.csv](xdr_field_mapping.csv)，其中“已确认结构字段”仅指历史告警结构和固定样例已验证的字段角色；“接入日候选字段”必须由真实 OpenAPI/MCP schema 确认，不构成对厂商接口的断言。完整输入契约见 [xdr_input_contract.md](xdr_input_contract.md)。

### 11.3 特殊业务规则与错误边界

已有固定样例的 SQLi `high/80`、横向移动 `medium/65` 且 `sample_nature=synthetic_regression` 保持不变。名称为“WebShell蚁剑工具文件管理”且原始等级为“高危”的固定 XDR 专项样例保持 `critical/95`；该专项规则不得泛化为“所有真实 XDR 高危告警均为 `critical/95`”。真实平台严重性必须先由接入日确认的枚举经受控词典映射，再进入风险研判。

真实读取应使用固定且带时区的时间窗口，并且在平台确认后只选择页码分页或游标分页之一。跨页按稳定提供方 ID 去重，保留时间更完整、证据更多的记录并记录去重数量。认证/授权失败、网络超时、平台错误、响应解析失败、字段校验失败和请求成功但零记录必须分类处理；其中 `records=[]` 是 `success + zero_records`，不代表连接失败，也不得生成虚假 `SecurityEvent`。固定样例中的 RFC 5737 文档地址只用于离线回归，不能作为真实 XDR 或 MCP 查询实体。

### 11.4 本轮脱敏材料与接入前验收

| 材料 | 位置 | 作用 | 边界 |
|---|---|---|---|
| XDR 输入契约 | `docs/modules/platform-tools/xdr_input_contract.md` | 定义必填/可选字段、分页、去重、错误、零记录和脱敏规则。 | 不含真实接口信息或运行时实体。 |
| 字段映射表 | `docs/modules/platform-tools/xdr_field_mapping.csv` | 提供机器可读的字段角色、确定性与缺失处理。 | 候选字段需在接入日确认。 |
| 脱敏请求结构 | `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | 表达含时区窗口、筛选、分页和本地认证边界。 | 不包含真实 URL、认证头或凭据。 |
| 脱敏响应结构 | `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | 表达最小记录、分页、零记录和证据引用结构。 | 不包含真实事件、告警、资产 ID 或原始响应。 |
| 契约测试 | `tests/test_xdr_input_contract.py` | 验证两份结构、最小字段、资产/设备回退和脱敏边界。 | 不访问网络、真实 XDR 或 MCP。 |

接入日仅在本地受控环境用一条真实 XDR 事件验证 schema、认证、只读权限、时间语义、一条记录转换、分页去重和零记录/错误分类，并只记录脱敏结论。真实 IP、事件/告警/资产 ID、用户名、平台 URL、Token、Cookie、接入码、原始响应、截图和 PCAP 均不得进入 Git、测试夹具、文档、PR 或群聊。

> 本轮结论是“真实 XDR 输入契约已准备，可与既有固定 JSONL 下游链路衔接”；并不是“真实 XDR OpenAPI/MCP 已接入、已查询真实事件或已完成生产性能验证”。

## 11. T0828-06 真实 XDR 字段映射与输入质量补充（2026-08-30）

本节在陈敏负责的 PR #22 历史设计基础上追加，不删除或改写此前内容。本次代码基于回归后的最新 `main`，不采用 PR #28 中未经官方接线材料确认的自定义 `auth_code` 鉴权、签名头或请求实现。陈敏负责真实响应解析、字段映射、输入质量、证据追溯、稳定 ID 去重规则和兼容性测试；官方签名、凭据注入、真实 HTTP 接线和统一主链运行由对应负责人负责。

已确认的非敏感字段契约包括：`data.item` 告警列表、`uuId` 稳定标识、`firstTime/lastTime` 时间来源、`name` 事件名称、`severity` 严重度、`srcIp/srcPort` 与 `dstIp/dstPort` 网络字段、`hostIp` 受影响资产候选、`devSourceName` 来源设备候选和 `traceBackId` 证据追溯标识。时间支持秒或毫秒 Unix 时间戳，IP 和端口支持数组首个有效值。

真实记录继续映射到现有 `NormalizedAlertRecord`，再转换为现有 `AlertRecord`，不创建第二套上层告警对象。攻击阶段、平台置信度和 GPT 研判等扩展字段在现有模型没有一等字段时，通过已有 `scenario_fields` 保留，避免静默丢失。缺少稳定 ID、非法时间、非法端口、非法严重度、非法状态、列表成员类型错误和业务响应失败均应明确失败；固定样例 fallback 必须显式启用并标记来源。

仓库只记录字段存在性、类型、已观察枚举和映射关系，不记录真实告警 ID、真实 IP、资产名、Base URL、联动码、Token、Cookie 或原始响应。
