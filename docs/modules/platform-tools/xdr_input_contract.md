# 真实 XDR 输入契约与适配准备（已对齐官方真实字段）

> 本文档基于 **PR#22 原始草稿 @ 2026-08-27** 升级而来，对齐 **main @ e154343（含 PR#33 @ e3cca8f）** 上实际落地的官方真实字段、分页、签名和错误语义。
>
> 变更性质：PR#22 是 early-stage 契约草稿（字段名多为 `<PROVIDER_DEFINED>` 占位符）；main 在 PR#26→PR#28→PR#33 中对齐真实 XDR OpenAPI 后，所有占位符均替换为官方确认的字段名、类型和值。

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 原始任务 | `T0827-06`（PR#22，2026-08-27） |
| 升级任务 | `T0903-06`（PR#33 对齐后，2026-09-03） |
| 模块 | 平台工具（`platform-tools`） |
| 文档目的 | 为真实 XDR 只读接入提供**最终可审查的输入契约、字段映射、脱敏结构和验收口径**。不是猜测，是 main 上实际运行的契约。 |
| 适用基线 | `main@e154343`（已合并 PR#17/22/24/26/28/32(revert)/33/29） |
| 关联代码 | `src/sec_agent/platforms/xdr_openapi.py`、`src/sec_agent/platforms/raw_jsonl.py`、`src/sec_agent/core/config.py`、`src/sec_agent/domain/models.py`、`src/sec_agent/services/correlation.py` |
| 敏感信息规则 | 真实 IP、事件/告警/资产 ID、用户名、URL、Token、Cookie、接入码、原始响应和响应截图均不得进入 Git、群聊、测试夹具或本文档。 |

> 完整字段映射表见 [xdr_field_mapping.csv](xdr_field_mapping.csv)（20 条，含 PR#33 新增的分页/签名/去重/错误分级契约）。

## 2. 目标与非目标

**目标**：将真实 XDR OpenAPI 返回记录经适配层转换为当前主链可消费的 `AlertRecord`，保持固定 JSONL 回归路径、严重性专项规则和告警关联逻辑不变。

**非目标**：不在本文档中保存真实 XDR 地址、凭据、认证头值或原始响应。这些内容仅在本地 `.env` 或受控运行环境保存。

## 3. 适配边界与数据流

```text
真实 XDR OpenAPI POST /api/xdr/v1/alerts/list
  → XdrOfficialSigner 签名（HMAC-SHA256, auth_code/aksk/token）
  → POST + JSON body {page, pageSize, startTimestamp?}
  → XDR response envelope（data.item[] + total + page + pageSize）
  → XdrOpenApiAdapter._to_normalizer_raw()（官方 camelCase → snake_case + 数组取首 + 时间优先链）
  → RawJsonlNormalizer._normalize_xdr()（severity 数字/中文双路径 + threatSubTypeDesc 威胁分类链 + destination→host 回退）
  → NormalizedAlertRecord（标准化中间契约）
  → AlertRecord（主链消费契约，_with_raw_context 追加 30 个 xdr_ 原始字段 + traceBackId EvidenceRef）
  → Orchestrator → AlertCorrelationService → triage/investigation/decision
```

## 4. 最小字段映射（官方真实字段，不再有占位符）

| 外部 XDR 字段角色 | 官方真实字段 | `NormalizedAlertRecord` 目标 | `AlertRecord` 目标 | 必填级别 | 转换与缺失规则 |
|---|---|---|---|---|---|
| **稳定唯一标识** | `uuId`（官方确认）；回退链 `event_id → alert_id → uuid → id → sample_id` | `event_id` | `alert_id` | 必填 | PR#22 候选：event_id/alert_id/id；PR#33 升级：uuId 为官方确认唯一标识。选择提供方稳定、可跨分页去重的标识；不得使用列表序号。无稳定标识 → ValueError（不降级）。 |
| **发生时间** | `lastTime → firstTime → updateTime`（官方 int Unix 秒戳，不是 ISO8601） | `event_time` | `occurred_at` | 必填 | PR#22 假设 ISO8601；PR#33 升级：Unix 秒戳 → `_time_to_text()` 用 `datetime.fromtimestamp()` 取墙钟 → normalizer 补 `+08:00`。优先顺序 lastTime（最新）→ firstTime → updateTime。全部缺失 → ValueError。⚠️ 隐含部署假设：服务器时区 = Asia/Shanghai。 |
| **告警名称** | `name`（官方真实字段）；回退链 `alert_name → rule_name → title` | `rule_or_event_name` | `name` | 必填 | trim whitespace；空值拒绝记录。 |
| **事件分类** | `threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name`（6 层优先链） | `event_type` | `alert_type` | 条件必填 | PR#22 只有 `alert_classification` 一个候选；PR#33 升级：官方有 threatSubTypeDesc 等分类字段。受控枚举 `sql_injection / webshell / lateral_movement / unauthorized_access / other`。未知值 → `other` 并在 scenario_fields 留痕。 |
| **原始严重性** | `severity`（**int**，官方观察值 50/70/90+）；回退 `alert_grade`（中文 严重/高危/中危/低危） | `severity` | `raw_severity` | 必填 | **数字路径优先**：≥90→critical/90，≥70→high/80，≥50→medium/65，<50→low/30。中文回退：严重→critical、高危→high、中危→medium、低危→low。⚠️ WebShell蚁剑工具文件管理 + "高危" 字符串专项升级（critical/95）与数字路径未统一。 |
| **源地址** | `srcIp`（**array\<string\>**，官方类型）；回退 `source_ip / src / sourceIps / srcIps` | `source_ip` | `src_ip` | 可选 | `_first_value()` 取数组首非空；全部为空数组或 null → None。不填充空串或 0.0.0.0。 |
| **源端口** | `srcPort`（**array\<int\>**）；回退 `source_port / srcPorts / srcPorts` | `source_port` | `src_port` | 可选 | `_first_value()` 取数组首非空 int（0..65535）。 |
| **目的地址** | `dstIp`（**array\<string\>**）**优先**；回退 `hostIp`（官方单值字段） | `destination_ip` / `affected_asset` | `dst_ip` / `assets` | 条件必填 | dstIp 取首 → 回退 hostIp 单值；address 优先作 assets 主值。两者均无 → 标注资产缺口。 |
| **目的端口** | `dstPort`（**array\<int\>**）；回退 `destination_port / dstPorts` | `destination_port` | `dst_port` | 可选 | 同源端口规则。 |
| **来源设备** | `devSourceName`（array）→ `engineName`（array）→ `devUidDesc`（array）→ `data_source` → 常量 `XDR` | `source_device_name` | `scenario_fields.source_device_name` | 必填 | `_first_text()` 取数组首非空；全部缺失回退常量 "XDR"。 |
| **证据追溯** | `traceBackId`（**array\<string\>**，官方证据回溯 ID） | `evidence_refs` | `evidence_refs` | 必填 | PR#33 升级：`traceBackId` 每项生成 `EvidenceRef(kind="xdr_traceback")`，ref_id 格式 `alert_id:traceBackId:{id}`。空数组跳过，不伪造证据。 |
| **数据来源** | 内部固定值 | `evidence_source` | `source` + `scenario_fields` | 必填 | PR#22 建议 source=xdr；PR#33 升级：固定 `source="xdr_openapi"` 区分后端类型，`evidence_source="xdr_security_alert"`。 |
| **原始字段留存** | 30 个官方字段白名单（见 CSV MAP-015） | — | `scenario_fields.xdr_*` | 可选 | PR#33 新增：`_with_raw_context()` 统一白名单，过滤条件 `value not in (None, "", [], {})`。空数组/null 不入场景字段。 |

## 5. 必填、可选和拒绝规则

一个记录只有在取得**稳定唯一标识（uuId 等）**、**可解析发生时间（lastTime 等）**、**非空告警名称（name）** 时，才可转换为 `AlertRecord`。事件类型可由 threatSubTypeDesc/riskTag 等受控词典推断为 `other`；源/目的地址、端口和资产扩展信息可以缺失，但缺失必须显式记录为证据缺口，不能捏造默认地址或资产。

> 与 PR#22 原始草稿的差异：PR#22 列了 4 个必需字段（稳定 ID + 时间 + 名称 + 严重性）；PR#33 把严重性从必需降级为"数字/中文双路径覆盖后总有值"——severity 在 main 上不会缺失，数字 50/70 总能命中分级。

## 6. 请求、响应与分页契约（已对齐官方真实值）

**不保存真实 XDR OpenAPI 请求或响应**。可审查的无真实值结构位于：

- [xdr_list_alerts_request_sanitized.json](../../tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json)
- [xdr_list_alerts_response_sanitized.json](../../tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json)

| 维度 | PR#22 原始草稿（早期占位符） | main @ e154343（PR#33 对齐后） |
|---|---|---|
| HTTP Method | `PROVIDER_DEFINED` | **POST** |
| Endpoint | `PROVIDER_DEFINED_NOT_COMMITTED` | **`/api/xdr/v1/alerts/list`**（config 默认值） |
| 鉴权 | `LOCAL_ENV_OR_SECRET_STORE_ONLY` | **XdrOfficialSigner HMAC-SHA256**（auth_code 14 段 → AES 解密 → ak/sk → HMAC；或 aksk 直接用；或 token Bearer） |
| 请求体 | `time_range.start_time=<ISO8601>`、`pagination.strategy=PROVIDER_DEFINED_PAGE_OR_CURSOR` | **JSON body `{"page":int, "pageSize":50, "startTimestamp":int?}`** |
| 响应顶层 | `data.records[]` + `pagination.has_next / next_page_token / total_count` | **`data.item[]`（单数字段）+ `total / page / pageSize`** |
| 唯一标识字段 | 候选：`event_id / alert_id / id` | **官方确认：`uuId`**（camelCase） |
| severity 类型 | 候选：`<PROVIDER_SEVERITY_ENUM>` | **官方确认：`int`**（已观察值 50/70/90+） |
| 时间类型 | 候选：`<ISO8601_WITH_TIMEZONE>` | **官方确认：`int Unix 秒戳`**（`lastTime / firstTime / updateTime` 三字段同时存在） |
| 分页方式 | 游标分页候选（`page_token`） | **页码式分页**（官方使用 page + pageSize + total，不是 cursor） |
| 翻页终止 | 游标 `has_next=false` / `next_page_token=null` / `total_count` | `page × alert_page_size >= total`；防御上限 `alert_max_pages=20` |
| 跨页去重 | 稳定 XDR 标识 | **`uuId`（优先）或整条 JSON 序列化兜底** |

## 7. 错误、空结果与去重规则（已对齐 PlatformIngestError 六类）

| 场景 | 适配层处理 | 对主链的影响 | allow_fallback（降级开关） |
|---|---|---|---|
| **auth**（401/403） | `kind="auth"`，`retryable=False`，日志仅记录脱敏错误类别 | 不生成虚假告警；由人工修正本地凭据 | ❌ False |
| **timeout**（连接超时/读取超时） | `kind="timeout"`，`retryable=True`，有限次数重试 | 本批次标记不完整，不能写成"无告警" | ✅ True |
| **unreachable**（DNS/连接拒绝） | `kind="unreachable"`，`retryable=True` | 同 timeout | ✅ True |
| **platform_error**（5xx / HTTP 4xx / 业务 code ≠ Success） | `kind="platform_error"`，5xx 可重试，4xx 不重试 | 拒绝该页或该记录，保留受控本地引用 | ❌ False（业务错误）/ ✅ True（5xx） |
| **field_mapping**（缺必需三字段 / ValidationError） | `kind="field_mapping"`，`retryable=False` | 拒绝该记录；其余合格记录继续；不得用列表下标补 ID | ❌ False（永不降级） |
| **empty_result**（item=[] 或全部被精确 lookup 过滤） | `kind="empty_result"`，`retryable=True` | **不是 transport failure，但主链视为"无可消费告警"**；走 APPROVAL_REQUIRED 终态（无 alert_refs） | ✅ True（允许降级到固定样例） |
| **跨页重复** | fetch 阶段 `seen_ids: set[str]` 按 uuId（兜底整条 JSON 序列化）去重 | 防止重复告警被误判为多起安全事件；同一 uuId 保留首次出现 | — |
| **关联压缩** | correlation 阶段按"同类型 + 同资产 + 同设备 + 15min 窗口"四条件二次压缩 N→1 | 不人为拆分同窗口内同类同源事件 | — |
| **固定样例查询真实 MCP/XDR** | RFC5737 IP 与占位 ID 不作为真实查询实体 | 预期零命中，应走 `no_data/人工接管` 而非伪造证据 | — |

## 8. 脱敏与运行时实体桥接（PR#22 原始契约，main 已落地）

- IP → RFC 5737 文档保留地址（198.51.100.x）
- ID → `<REDACTED_*>` 语义占位符
- 时间 → 整体平移或 `<INTEGER_UNIX_SECONDS>` 占位符
- 原始字段 → 带 `xdr_` 前缀留存（30 个白名单字段，过滤 None/""/[]/{}）
- 真实端点 URL / token / auth_code → **不得**出现在 Git 仓库任何位置
- 运行时调试响应 → `*.local.json`（已在 .gitignore），验证后删除

## 9. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-08-27 | 首次建立（PR#22） | early-stage 草稿，字段名多为 `<PROVIDER_DEFINED>` 占位符；不包含适配器实现 |
| 2026-08-28~29 | PR#26/28 迭代 | 出现真实适配器雏形但无官方签名 |
| 2026-08-29 | PR#32 全盘 revert | 上一轮真实映射被判定为过早提交 |
| 2026-08-30 | PR#33 `0c03b1f~e3cca8f` | 对齐官方真实字段：POST /api/xdr/v1/alerts/list + XdrOfficialSigner + uuId + item 分页 + 数字 severity + Unix 秒戳 + threatSubTypeDesc 链 + lastTime 优先 + 30 字段留存 + PlatformIngestError 六类 |
| 2026-09-03 | T0903-06 升级本文档 | 从 PR#22 原始草稿升级到官方真实字段，标注每个字段的"PR#22 候选 → PR#33 升级"演变 |
