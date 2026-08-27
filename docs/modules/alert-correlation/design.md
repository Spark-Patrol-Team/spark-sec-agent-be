# 告警接入与关联模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联） |
| 负责人 | 陈敏 |
| 文档状态 | 当前有效 |
| 实现状态 | 已复验 |
| 能力性质 | 自研代码 + 固定 JSONL fallback + Mock 主链；不含真实平台实时接入。 |
| 关联任务/需求 | `T0826-06`｜固定 JSONL 告警接入关联回归与文档补齐。 |
| 关联正式交付章节 | `docs/deliverables/安全智能体系统设计说明书V2.md`：模块设计、统一事件上下文、主流程与状态流转、平台接入边界。 |
| 对应 PR/Commit | PR #17；`1a5bbf1`（后续文档模板对齐提交追加到同一 PR）。 |
| 最后更新时间 | 2026-08-26 |
| 最后复验时间 | 2026-08-26（基于最新 `main@95defad` 与 PR #17 内容的隔离联调）。 |

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
