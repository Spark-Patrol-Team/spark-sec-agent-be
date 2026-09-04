# T0903-06 下游摘要（二）：给杨景凡的调查实体/证据引用摘要

> 接收人：杨景凡（统一候选交接确认）
> 撰写人：陈敏（字段确认人）
> 基线 Commit：`main@e154343`（含 PR#33 `e3cca8f`）+ 本任务提交 `9c6f00d`
> 稳定字段契约版本：`2026-09-03.t0903-chenmin-v1` + `xdr_field_mapping.csv` XDR-MAP-001 ~ MAP-020
> 契约文件：`docs/modules/platform-tools/xdr_field_mapping.csv`、`docs/platform-tools/t0903-06-step2-contract-package.md`

---

## 一、可以用于 MCP 查询的实体（统一候选来源与字段来源）

调查工具（尤其是证据查询类 MCP/工具）的查询参数应优先从 `SecurityEvent.entities` 构造。该字典由 `AlertCorrelationService.correlate()` 统一聚合，**跨页去重后、窗口压缩后、实体集合再次 set 去重**，字段来源可追溯。

| 实体名（MCP 入参） | `SecurityEvent.entities` 键 | 单告警来源字段（XDR 官方字段） | 是否经过脱敏 | 备注 |
|---|---|---|---|---|
| **源 IP 列表** | `src_ips: list[str]`（已去重） | `AlertRecord.src_ip` ← `srcIp[]` 取首（官方 array<string>） | ✅ 真实 XDR 响应中的 IP **未经脱敏**，是实际攻击流量 IP，可直接用于 MCP 查询 | ⚠️ 固定样例/契约测试 fixtures 中 IP 是 RFC 5737 文档地址（198.51.100.x），**不能用于真实查询**，见下文 §3。 |
| **目的 IP 列表** | `dst_ips: list[str]`（已去重） | `AlertRecord.dst_ip` ← `dstIp[]` 首 → 回退 `hostIp`（单值 string） | ✅ 真实响应中是实际受害资产 IP，可直接用 | 同 src_ips 脱敏边界；dstIp 与 hostIp 同时空时，dst_ips=[]。 |
| **受害资产列表** | `assets: list[str]`（已去重） | `AlertRecord.assets` ← `affected_asset` = `destination_ip`（dstIp 首 → hostIp 回退） | ✅ 真实资产 IP | 若 assets=[]，应改为用 dst_ips 查询。 |
| **来源设备列表** | `source_devices: list[str]`（已去重） | `AlertRecord.scenario_fields.source_device_name` ← `devSourceName[] → engineName[] → devUidDesc[]` | ✅ 来源设备名未经脱敏，可用于平台定向查询 | 三字段全空时回退常量 `"XDR"`，此时应改用 IP 查询。 |
| **告警 ID 列表**（非 entities 字段，但必需） | `SecurityEvent.alert_refs: list[str]` | `AlertRecord.alert_id` ← 官方 `uuId`（稳定唯一标识） | ✅ 真实 uuId 是 XDR 后端实际 ID，可直接追溯 | ⚠️ 固定样例和契约测试中的 `alert_id` 是占位符或 `xdr-alert-00*` 假值，**不能用于真实查询**。 |
| **事件 ID** | `SecurityEvent.event_id: str` | 由关联服务自动生成 `evt-{uuid4}`（主链内 ID，不是 XDR 后端 ID） | N/A | ❌ 不能用于 MCP/XDR 查询，仅在本系统上下文内有效。**调查查询必须使用 alert_refs 而非 event_id。** |
| **时间范围**（字段来源） | `SecurityEvent.first_seen_at` ~ `last_seen_at`（已关联窗口压缩） | `AlertRecord.occurred_at` ← `lastTime → firstTime → updateTime`（官方 int Unix 秒戳） | N/A | ✅ 真实时间范围，可用于日志/MCP 的时间窗口参数。⚠️ 统一用 ISO8601 带时区字符串，不要用原始 xdr_lastTime int 戳反推墙钟。 |
| **事件类型（MCP 场景参数）** | `AlertRecord.alert_type` + 关联服务 `alert_types` 聚合 | `threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name` | N/A | ✅ 枚举 `sql_injection/webshell/lateral_movement/unauthorized_access/other`。固定样例和真实路径一致。 |

---

## 二、警告 ID 或事件 ID（调查参数必带字段）

| 字段 | 代码来源 | 类型 | **是否仍可能为空** | 备注 |
|---|---|---|---|---|
| **`alert_refs[]`**（每条告警唯一 ID） | `SecurityEvent.alert_refs` ← `[AlertRecord.alert_id for alert in ordered_alerts]` | `list[str]`（官方 `uuId` 列表） | ❌ 永不空（无告警时关联服务直接 ValueError，不会走到调查阶段） | **调查唯一 ID 真相来源**：所有 XDR 后端告警查询/日志追溯都应以 alert_refs 为锚，不要用 SecurityEvent.event_id（主链自动生成）。 |
| **`event_id`**（主链内部 ID） | `SecurityEvent.event_id` ← `evt-{uuid4}`（自动生成） | `str` | ❌ 永不空 | ❌ 仅用于本系统仓储和 API 查询响应，**不能用于 MCP 或真实 XDR 查询**。 |
| **`trace_id` / `run_id`**（跨模块追踪） | `EventContext.trace_id` / `EventContext.run_id` ← Orchestrator 启动时生成 | `str` | ❌ 永不空 | 用于工具调度、审批和日志关联，不用于 XDR 查询。 |

---

## 三、IP、资产、时间范围等字段的来源（逐字段代码映射链）

| 调查参数 | 代码字段 | 官方 XDR 字段 → 标准化映射链 | 可能为空？ |
|---|---|---|---|
| MCP 查询：源 IP | `entities.src_ips[0]` / `src_ip` | XDR 官方 `srcIp: array<string>` → `_first_value(raw, "srcIp", "source_ip", "src", "sourceIps", "srcIps")` → `NormalizedAlertRecord.source_ip` → `AlertRecord.src_ip` → 关联服务 `set.add` 去重 | ✅ 可能（srcIp 全空数组 → None → 不入 set → src_ips=[]） |
| MCP 查询：目的 IP | `entities.dst_ips[0]` / `dst_ip` | XDR 官方 `dstIp: array<string>` → `_first_value(...)` → 回退 `hostIp`（单值 string）→ `NormalizedAlertRecord.destination_ip` → `AlertRecord.dst_ip` | ✅ 可能（dstIp + hostIp 同时缺失 → None → dst_ips=[]） |
| MCP 查询：受害资产 | `entities.assets[0]` | = `destination_ip`（mapping.csv 规则 16/23-26 一致：以 destination_ip 作为 affected_asset）→ `AlertRecord.assets = [affected_asset]` | ✅ 可能（destination 缺失 → assets=[]） |
| MCP 查询：设备 | `entities.source_devices[0]` | `devSourceName: array<string>` 首 → 回退 `engineName[]` 首 → 回退 `devUidDesc[]` 首 → 常量 `"XDR"` | ❌ 永不空（恒有 "XDR" 兜底） |
| MCP 查询：开始时间 | `first_seen_at` | 按 occurred_at 升序排列的 `alerts[0].occurred_at`（lastTime 优先）→ `SecurityEvent.first_seen_at` | ❌ 永不空 |
| MCP 查询：结束时间 | `last_seen_at` | 按 occurred_at 升序排列的 `alerts[-1].occurred_at` → `SecurityEvent.last_seen_at` | ❌ 永不空 |
| MCP 查询：事件类型场景 | `alert_type` | `threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name` | ❌ 永不空（未知值强制落 "other"） |

---

## 四、哪些实体经过脱敏，不能直接用于真实查询或真实 MCP 数据源

⚠️ **以下实体来源于测试 fixtures 或固定样例路径，是脱敏占位，绝对不能用于真实 MCP/XDR 查询：**

| 来源路径 | 脱敏对象 | 脱敏形式 | 如何识别 |
|---|---|---|---|
| `source=fixed_sample`（固定样例） | 所有 IP / ID / URL / 设备名 | RFC 5737 文档地址 `198.51.100.x` / `alert_id=xdr-alert-00*` / 假 traceBackId | `EventContext.effective_source="fixed_sample"` 或 `EventContext.requested_source="fixed_sample"` |
| `source=jsonl_sample` | 同上 | 同上 | `effective_source="jsonl_sample"` |
| 契约 fixtures：`tests/fixtures/xdr_openapi/*.json` | 所有实体 | `192.168.X.X / 192.168.Y.Y`（X 掩码）/ `alert-REDACTED-UUID` / `<REDACTED_*>` | 仅 pytest 加载，不进入实际运行 |
| 契约 fixtures：`tests/fixtures/xdr_contract/*.json` | 所有实体 | `<REDACTED_RUNTIME_*>` / `<INTEGER_UNIX_SECONDS>` / `<PROVIDER_*>` 占位符 + RFC 5737 地址 | `fixture 根键 contract_version` 存在，仅契约测试引用 |
| `platform_fallback=True` 时 | 实体与 fixed_sample 相同（fallback 来源是固定样例） | 同上 | `AlertRecord.scenario_fields.platform_fallback=True` 且 `AlertRecord.source="fixed_sample_fallback"` |

✅ **真实路径标识**：当 `EventContext.effective_source="xdr_openapi"` 且 `fallback_source=None` 且 `AlertRecord.scenario_fields.platform_fallback` 不存在时，所有实体是真实 XDR 返回值——此时 `src_ips / dst_ips / assets / alert_refs(uuId) / 时间范围 / source_devices` 均可直接用于真实 MCP 查询或 XDR 后端追溯。

---

## 五、哪些字段可能不存在（调查查询前应做 exists 判断）

以下字段在**合法输入下也可能不存在/为空列表/None**，MCP 工具调用前应判断后使用：

| 调查参数 | 为空条件 | 为空时建议做法 |
|---|---|---|
| `entities.src_ips` / `src_ip` | XDR 官方 `srcIp=[]` 或全部 None | 跳过源 IP 维度查询，或从 `scenario_fields.xdr_srcIpInfos[0].ip` 尝试（若存在） |
| `entities.dst_ips` / `dst_ip` | `dstIp=[]` 且 hostIp 缺失 | 跳过目的 IP 查询，或从 `xdr_dstIpInfos[0].ip` 尝试 |
| `entities.assets` | `destination_ip` 为空且 `host_ip` 缺失 | 使用 `dst_ips` 作资产替代查询；若仍空则标记证据缺口需人工补填 |
| `entities.source_devices` | 仅在 `"XDR"` 兜底（`devSourceName/engineName/devUidDesc` 全空）且设备名对平台查询不敏感时 | 改用 IP 维度 + 时间窗口查询；若平台只按设备名查询，需人工提供 |
| `evidence_refs`（调查阶段证据链） | `traceBackId=[]` 且标准化字段引用为空时 | 调查第一步直接打 `TriageResult.evidence_gaps` 标记；人工从 XDR 原始告警补查 |
| `src_port / dst_port` | `srcPort=[]` / `dstPort=[]` | MCP 工具参数不传或传 0 占位，不在查询条件中加入 |
| `scenario_fields.xdr_traceBackId`（原始字段，用于日志追溯） | traceBackId 空数组时整个 key 被过滤掉 | 用 `alert_id`（uuId）作为日志查询替代锚点 |

---

## 六、可引用的证据 ID（调查闭环引用格式）

两类证据引用，均与 `AlertRecord` 绑定，是调查工具（如 `evidence_lookup`）和报告必须使用的格式：

| 证据种类 | `kind` 值 | `ref_id` 格式 | 代码生成位置 | 可否用于真实追溯 |
|---|---|---|---|---|
| 标准化字段引用 | `xdr_field` | `{alert_id}:{field_name}`（例：`alert-uuid:name`） | `_from_normalized()` 批量生成 `EvidenceRef` | ❌ 仅表示该字段值作为研判证据使用（引用在系统内），**不代表**可直接查到 XDR 后端原始条目。 |
| 原始日志追溯 ID（最关键） | `xdr_traceback` | `{alert_id}:traceBackId:{trace_id}`（例：`alert-uuid:traceBackId:network_security_log-001`） | `_with_raw_context()` 从 XDR 官方 `traceBackId: array<string>` 逐条 append | ✅ 真实路径下，trace_id 是 XDR 后端实际日志追溯号，可用于 MCP 或安全运营人员直查。固定样例/契约 fixtures 中 trace_id 是假值。 |
| 原始记录引用 | N/A（`raw_record_ref` 字段） | `xdr://openapi/alerts#{uuId}`（真实）/ `xdr://jsonl#{id}`（样例）/ `fallback+xdr://…`（降级） | `XdrOpenApiAdapter.fetch_alerts()` 直接写入 | ✅ 用于证据审计链条追溯。`fallback+` 前缀时意味着该告警是降级固定样例，**不能用于真实查询**。 |

---

## 七、当前对应代码 Commit

- **实体聚合**：`9c6f00d` → `src/sec_agent/services/correlation.py:23-71`（15 分钟关联窗口 + `src_ips/dst_ips/assets/source_devices` 四集合 set 去重）
- **告警 → AlertRecord 映射链**：`9c6f00d` → `src/sec_agent/platforms/xdr_openapi.py:335-509`（`_to_normalizer_raw()` + `_with_raw_context()`）
- **标准化中间契约**：`e154343` → `src/sec_agent/domain/models.py:115-138`（`NormalizedAlertRecord`，所有调查实体上游字段）
- **证据引用生成**：`9c6f00d` → `xdr_openapi.py:440-447`（xdr_field 引用）+ `489-501`（xdr_traceback 引用）

---

## 八、调查注意事项（给杨景凡）

1. 🔍 **统一候选必须使用 `SecurityEvent.alert_refs`，禁止用 `SecurityEvent.event_id` 做 XDR 后端查询**——event_id 是主链生成的内部 ID，不是 XDR 的 uuId。
2. 🛡️ **工具参数调用前必做 exists 判断**：`src_ips/dst_ips/assets/source_devices/ports/evidence_refs` 七项在契约中都允许为空，MCP 查询前必须判断，空时走替代查询维度或打 `evidence_gap`，**不要塞 "0.0.0.0" 或 "" 等默认值**。
3. 🧪 **fixture 识别规则**：所有 `<REDACTED_*>` 占位符、`198.51.100.0/24`、`192.168.X.X`、`xdr-alert-00*` 前缀的告警 ID、`fallback+` 前缀的 raw_record_ref，**一律视为脱敏，不进入真实 XDR/MCP 查询**。
4. ⏱️ **时间窗口传递**：调查工具时间参数必须使用 `first_seen_at` / `last_seen_at` 的 ISO8601 字符串（自带 `+08:00`），**不使用 `xdr_firstTime/xdr_lastTime` 的 int 戳**——避免服务器时区墙钟不同导致的时间偏移。
5. 📌 **证据闭环引用格式**：报告中引用证据时必须使用 `ref_id` 完整格式（`{alert_id}:traceBackId:{id}` 或 `{alert_id}:{field}`），报告中出现的证据引用须与 `InvestigationReport.key_evidence_refs` 一致。
