# 告警接入与关联模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | `alert-correlation`（告警接入与关联） |
| 负责人 | 陈敏 |
| 文档状态 | 当前有效（T0903-06 补充真实 XDR 字段来源与证据链） |
| 实现状态 | 已复验 + 真实 XDR 适配；58 项逐字段核对完成（57 通过 1 待决策）；175 passed 基线 |
| 能力性质 | 自研代码 + XdrOpenApiAdapter 真实接入 + 固定 JSONL fallback + Mock 主链。 |
| 关联任务/需求 | `T0826-06` 固定 JSONL 告警接入关联回归；`T0903-06` 真实输入契约资产迁移（陈敏）。 |
| 关联正式交付章节 | `docs/deliverables/安全智能体系统设计说明书V2.md`：模块设计、统一事件上下文、主流程与状态流转、平台接入边界。 + `docs/platform-tools/t0903-06-step2-contract-package.md`（字段契约包）。 |
| 对应 PR/Commit | PR #17；PR#33 merge 点 `main@e154343`；T0903-06 提交 `9c6f00d`。 |
| 最后更新时间 | 2026-09-04（T0903-06：真实 XDR 字段来源、空/去重/分页契约对齐、证据缺口与实体集合更新） |
| 最后复验时间 | 2026-09-04（基于 `9c6f00d`，恶劣环境下 21 条契约回归 + 4 条 PR#22 升级测试 + 原有 JSONL 关联 17 项全部通过）。 |

## 1. 目标与非目标

### 1.1 目标

- 读取固定 JSONL / 真实 XDR 两种脱敏来源告警，在 `raw` 或 `normalized` 输入模式下转换为统一 `AlertRecord`。
- 按固定样例契约 + 真实 XDR 官方字段契约双路径复验严重性、受影响资产、来源设备和证据引用映射（58 项逐字段核对，57 通过 1 待决策）。
- 将同一候选攻击活动在 15 分钟窗口内关联为一个 `SecurityEvent`，**保留参与告警、实体（src_ips/dst_ips/assets/source_devices 四集合 set 去重）、关联依据和压缩前后数量**。
- 为下游风险研判和深度调查提供 `alert_refs`（真实 XDR uuId）、稳定字段的 `first_seen_at / last_seen_at` 时间窗口和实体集合，便于 MCP 查询。
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
| `POST /api/xdr/v1/alerts/list` 响应 | JSON（带 official `data.item[]` 壳） | `PLATFORM_BACKEND=xdr_openapi` 必填 | `XdrOpenApiAdapter.fetch_alerts()` | 契约文档：`docs/modules/platform-tools/xdr_input_contract.md`。唯一标识 `uuId`；时间 `lastTime→firstTime→updateTime` 优先；数组字段 `srcIp/dstIp/srcPort/dstPort/riskTag/devSourceName` 等取首非空。 |
| `StartRunRequest.xdr_event_id` | `str \| None` | 否 | 用户启动请求 | 真实路径下按 `uuId` 在所有已拉取告警中本地精确匹配；不依赖上游按 uuId 过滤接口。 |
| `AlertRecord` 列表 | `list[AlertRecord]` | 是 | `JsonlSampleAdapter` / `XdrOpenApiAdapter` / `AlertIngestService` | 必须属于同一候选攻击活动后才可传入关联（同 event_type/同 assets/同 source_device/同 15min 窗）。 |
| `JSONL_INPUT_MODE` | `normalized` / `raw` | 否 | 配置 | `normalized` 直接读取标准化样例；`raw` 先标准化后适配。 |
| `fetch_alerts(xdr_event_id=)` | `list[AlertRecord]` | 必填（真实路径） | `XdrOpenApiAdapter` | 已按 `uuId`（优先）或整条 JSON 兜底在分页跨页间去重，不会产生重复事件。 |

### 3.2 输出

| 字段/对象 | 类型 | 去向 | 含义与约束 |
|---|---|---|---|
| `AlertRecord` | `AlertRecord` | `AlertIngestService`、`Orchestrator` | 保留告警 ID（uuId）、时间（lastTime 优先）、类型、严重性、资产、样例性质、字段级证据和原始记录引用。真实路径下 scenario_fields 含 30 个 xdr_* 前缀原始字段 + evidence_refs 追加 traceBackId（`kind=xdr_traceback`）。 |
| `SecurityEvent` | `SecurityEvent` | `EventContext.event_summary`、`RiskTriageService`、DeepInvestigationAgent | 包含 `alert_refs`（真实 uuId）、时间范围 `first_seen_at/last_seen_at`（occurred_at 排序两端）、`entities`（`src_ips/dst_ips/assets/source_devices` 四个 set 去重集合，给 MCP 查询用）、`correlation_reason`、`alert_count_before`、`event_count_after` 和摘要。 |
| 关联异常 | `ValueError` | `Orchestrator` 错误处理与上层拆分逻辑 | 空输入、事件类型/资产/设备不一致或超过 15 分钟窗口时拒绝合并。真实 XDR uuId 跨页重复不会产生此异常（fetch 阶段已按 seen_ids 去重）。 |

## 4. 核心流程与状态变化

1. 平台适配器按来源读取告警：
   - **JSONL/固定样例路径**：`JsonlSampleAdapter` 按输入模式读取；raw 模式调用 `RawJsonlNormalizer`，normalized 模式校验 `NormalizedAlertRecord`。
   - **真实 XDR 路径**：`XdrOpenApiAdapter` 以 `XdrOfficialSigner` 签名 POST `/api/xdr/v1/alerts/list`，按 `{page,pageSize,startTimestamp}` 分页，`total` 或 `alert_max_pages=20` 终止；`seen_ids` 按 `uuId`（或整条 JSON 兜底）跨页去重；若请求指定 `xdr_event_id`，在全量拉取后按 `uuId` 本地精确匹配。
2. 适配器生成 `AlertRecord`，写入 `source_device_name`（`devSourceName→engineName→devUidDesc→"XDR"` 回退链）、`affected_asset`（destination→host 回退）、`sample_nature`（真实路径固定 `platform_derived`）、`risk_score_seed`（数字 severity 优先映射）、`evidence_refs`（标准化字段引用 + traceBackId 追加）与 `raw_record_ref`（`xdr://openapi/alerts#{uuId}` 前缀）。
3. `AlertIngestService` 将告警交给 `Orchestrator`；编排器记录 `RECEIVED` 后进入 `CORRELATING`。
4. `AlertCorrelationService` 校验事件类型、目标资产、来源设备和 15 分钟窗口，生成 `SecurityEvent`（`entities` 字段四集合去重：`src_ips/dst_ips/assets/source_devices`），写入 `EventContext.event_summary`。
5. 编排器调用 `RiskTriageService.triage(event, alerts)`，记录 `TRIAGED`；后续调查、决策、审批、Mock 处置和验证仍由其他模块及编排器推进。
6. 关联条件不满足或接入失败时，模块返回可读异常；编排器记录错误并转入相应失败/人工路径，不产生伪造的关联事件。真实 XDR `PlatformIngestError` 六类错误语义（auth/platform_error/field_mapping/empty_result/timeout/unreachable）统一经 orchestrator.errors 记录。

关联模块不直接修改 `EventContext.status`；所有状态变化仅由 `src/sec_agent/services/orchestrator.py` 与状态机推进。

## 5. 上下游关系与契约

| 方向 | 模块/接口 | 契约或文档位置 | 当前状态 |
|---|---|---|---|
| 上游 | 固定样例 | `tests/fixtures/fixed_alerts/`、`NormalizedAlertRecord` | 已对齐。 |
| 上游 | 真实 XDR 官方脱敏响应 | `docs/modules/platform-tools/xdr_input_contract.md` + `tests/fixtures/xdr_contract/` + `tests/fixtures/xdr_openapi/official_desensitized_alert.json` | 已对齐，20 条官方字段映射 CSV + 25 条契约回归。 |
| 上游 | 平台适配器 | `src/sec_agent/platforms/xdr_openapi.py`（真实 XDR）、`jsonl_sample.py`、`raw_jsonl.py`（标准化） | 已对齐。 |
| 当前模块 | 关联服务 | `src/sec_agent/services/correlation.py` | 已对齐，最小 15 分钟规则 + 四条件校验 + 实体集合去重。 |
| 下游 | 风险研判 | `src/sec_agent/services/triage.py`、`RiskTriageService.triage(event, alerts)` | 已对齐。研判字段摘要（给闫昱硕）见 `docs/platform-tools/t0903-06-step4-summary-for-yanyushuo-judgment.md`。 |
| 下游 | 深度调查 | `src/sec_agent/services/investigation.py`、`DeepInvestigationAgent` | 已对齐。调查实体/证据摘要（给杨景凡）见 `docs/platform-tools/t0903-06-step4-summary-for-yangjingfan-investigation.md`。 |
| 下游 | 主链编排 | `src/sec_agent/services/orchestrator.py`、`EventContext` | 已对齐。 |
| 后续 | 调查/处置/前端 | `EventContext.event_summary`、`triage`、`investigation`、`response` | 已对齐，具体业务由对应模块负责。 |

---

## 5.1 T0903-06 新增：字段核对结果与契约对齐表（给关联模块审阅）

以下是关联模块读取/写入的关键字段已确认：

| 关联模块字段 | 真实 XDR 来源 | 稳定？ | 可能为空？ | 核对结果 |
|---|---|---|---|---|
| `AlertRecord.alert_id` | 官方 `uuId`（唯一标识） | ✅ | ❌ | 通过（fetch 阶段 seen_ids 去重已验证） |
| `AlertRecord.occurred_at` | `lastTime → firstTime → updateTime`（int 戳 + Asia/Shanghai） | ✅ | ❌ | 通过（优先级链已 58 项核对） |
| `AlertRecord.alert_type` | 6 层威胁分类链 → 枚举 5 值 | ✅ | ❌（未知值落 `other`） | 通过（真实 8 条告警全覆盖） |
| `AlertRecord.assets[0]`（关联 target_asset） | dstIp[] 首 → hostIp 回退 | ✅ | ✅（空数组 + host 空时） | 通过（空时关联比对使用 dst_ip 兜底） |
| `source_device_name`（关联 source_device） | devSourceName→engineName→devUidDesc→"XDR" | ✅ | ❌（恒有 "XDR" 兜底） | 通过（15 分钟关联的设备比对稳定） |
| `SecurityEvent.entities`（四集合） | 各 AlertRecord 字段 set.add 聚合 | ✅ | 按源字段可能为空 | 通过（空字段不入集合，空集合调查摘要中有替代查询路径） |
| `SecurityEvent.alert_refs` | `AlertRecord.alert_id` 按时间有序 | ✅ | ❌ | 通过（uuId 稳定 + 关联验证 21 条回归） |

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
| 真实 XDR 分页翻页到 max_pages=20 后强制截断；不会静默降级，但会丢失更旧窗口之外的告警 | 不阻塞当前单次事件；阻塞大批量历史回溯 | 取得更多告警时增大 max_pages 或改为滚动时间窗口增量拉取。 |
| severity 数字 vs 字符串专项升级未统一（蚁剑 WebShell 固定样例 95 vs 真实 80） | 影响研判风险分差 15 | 钱诺成决策后，在 `RawJsonlNormalizer._xdr_severity()` 统一语义。 |
| 真实平台超时、限流、重试未实现 | 不影响固定样例；影响真实接入可靠性 | XdrOpenApiAdapter 接入时按 `PlatformIngestError.retryable` 字段实现重试。 |
| 调查 MCP 查询中，空实体集合（src_ips/dst_ips/assets）可能导致工具参数缺失 | 不阻塞主链状态流转；阻塞调查工具自动查询 | 调查摘要已给出 7 项必判 exists 字段 + 替代查询维度，杨景凡按其补填 `evidence_gaps`。 |
| 服务器时区不是 Asia/Shanghai 时，occurred_at 偏移 8 小时，导致 15 分钟关联窗口错位 | 不阻塞本地/Windows 测试；阻塞 Linux UTC 默认 CI/生产 | CI 与生产统一设置 TZ=Asia/Shanghai。 |

## 10. 变更记录

| 日期 | PR/Commit | 变更内容 | 是否复验 |
|---|---|---|---|
| 2026-08-25 | PR #17 / `1a5bbf1` | 新增固定 JSONL 告警接入关联专项回归与设计文档。 | 是，隔离环境专项 17 项和全量 70 项测试已执行。 |
| 2026-08-25 | PR #17 后续提交 | 对齐团队统一模块文档模板，补充文档信息、契约、证据、限制和变更记录。 | 文档事实与同一代码基线复核。 |
| 2026-08-26 | PR #17 后续联调提交 | 在最新 `main@95defad` 上重放 PR #17 内容，复测固定 JSONL、关联和风险研判衔接。 | 是，专项 17 项、全量 79 项测试均通过，框架 skipped 1；raw 主链到 `COMPLETED`。 |
| 2026-09-04 | `main@e154343` + `9c6f00d`（T0903-06） | 真实 XDR 适配：补充 uuId 跨页去重 + 官方分页/签名/错误分类；字段核对 58 项（57 通过 1 待决策）；175 passed 基线；为研判（闫昱硕）和调查（杨景凡）提供带 Commit 的下游摘要 2 份。 | 是（175 passed 全量 + 恶劣环境 3 项隔离复测通过）。 |
