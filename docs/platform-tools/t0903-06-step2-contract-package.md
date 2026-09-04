# T0903-06 陈敏：字段契约包

> 执行日期：2026-09-03
> 基线：`origin/main` @ `e154343`（已含 PR#33 `e3cca8f`）
> 来源：官方脱敏真实结构（XDR_OpenAPI更新版(1).md 第五部分 + 5.1 节最新观察）
> 代码映射链：`XdrOpenApiAdapter._to_normalizer_raw()` → `RawJsonlNormalizer._normalize_xdr()` → `NormalizedAlertRecord` → `_from_normalized()` → `AlertRecord` → `_with_raw_context()`

## 0. 版本信息
| 项目 | 值 |
|---|---|
| 契约版本 | `2026-09-03.t0903-chenmin-v1` |
| 依赖 Commit | `e154343` |
| 输入协议 | POST `/api/xdr/v1/alerts/list` + JSON body 分页 |
| 唯一标识 | `uuId` |
| 时间标准 | `lastTime`（优先）→ `firstTime` → `updateTime`；Unix 秒戳 + Asia/Shanghai |
| 分页语义 | 页码式 `page + pageSize + total + item`，`alert_max_pages=20` 上限 |
| 去重语义 | fetch 阶段基于 `uuId`（兜底整条 JSON 序列化）+ correlation 阶段按类型/资产/设备/窗口四条件二次压缩 |

---

## 1. 顶层返回契约（payload 路由）

```json
{
  "code": "Success",                 // string, 必填, 枚举: "Success"/"success"/"0" 视为业务成功, 其他 → PlatformIngestError(platform_error)
  "message": "成功",                 // string, 必填, 业务描述（code 非 Success 时用于错误信息）
  "data": {                          // object, 必填, 若缺失且根节点非 list → field_mapping 直接失败
    "total": 8,                      // int, 必填, 告警总数；bool/null/非数字 → None（由 _extract_total 兜底）
    "page": 1,                       // int, 可选
    "pageSize": 50,                   // int, 可选
    "item": [                        // array<object>, 必填, **单数字段**（不是 items）；空数组触发 empty_result
      { /* 单条告警对象 */ }
    ]
  }
}
```

> 路由逻辑见 [_extract_items()](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L278)：优先 `data.item` → 回退 `data.items` → 回退 `data` 为数组 → 回退根节点；非 dict/list 直接 raise ValueError。

---

## 2. 单条告警字段契约（官方脱敏结构字段清单）

### 2.1 必需字段（主链必需；缺失直接 `raise ValueError("缺少 event_id/alert_time/alert_name")`）

| 官方字段 | 类型 | 空值可能 | 映射目标 | 映射链 | 空值策略 |
|---|---|---|---|---|---|
| **`uuId`** | string | 否（本次非空） | `AlertRecord.alert_id` + `NormalizedAlertRecord.event_id` | `_alert_lookup_key()` 查找链首位，后接 `event_id, alert_id, uuid, id, sample_id` | 必选；若全部候选缺失 → ValueError |
| **`firstTime`** / **`lastTime`** / **`updateTime`** | int（Unix 秒） | 否（本次非空） | `AlertRecord.occurred_at` + `NormalizedAlertRecord.event_time` | `_first_time_text()` 优先级 `lastTime → firstTime → updateTime`；通过 `_time_to_text()` 把 int 戳转 ISO；无时区时由 normalizer 补 `+08:00` | 必选；若全部候选缺失 → ValueError |
| **`name`** | string | 否（本次非空） | `AlertRecord.name` + `NormalizedAlertRecord.rule_or_event_name` | `_first_text()` 查找链 `name → alert_name → rule_name → title`；空字符串视为缺失 | 必选；若全部候选缺失 → ValueError |

### 2.2 可选核心字段（映射到 NormalizedAlertRecord 主字段）

| 官方字段 | 类型 | 空值可能 | 映射目标 | 映射链 | 枚举/转换 |
|---|---|---|---|---|---|
| `severity` | **int**（已观察 50/70） | 否（本次非空） | `NormalizedAlertRecord.severity` + `AlertRecord.raw_severity` | → `alert_grade` → `_xdr_severity()` → 双路径 | **数字路径优先**：≥90→critical/90，≥70→high/80，≥50→medium/65，<50→low/30；若 `alert_name=="WebShell蚁剑工具文件管理" AND alert_grade=="高危"`（仅字符串）→ critical/95 专项升级 |
| `srcIp` | **array\<string\>** | ✅ 可能为空数组 | `NormalizedAlertRecord.source_ip` + `AlertRecord.src_ip` | `_first_value()` 取首非空 | 数组取首 → string；全部为空 → None |
| `srcPort` | **array\<int\>** | ✅ 可能为空数组 | `NormalizedAlertRecord.source_port` + `AlertRecord.src_port` | `_first_value()` 取首非空 | 数组取首 → int；全部为空 → None |
| `dstIp` | **array\<string\>** | ✅ 可能为空数组 | `NormalizedAlertRecord.destination_ip` + `AlertRecord.dst_ip` | `_first_value()` 取首非空 → 回退 `hostIp` | dstIp 全空或空数组时回退 hostIp |
| `dstPort` | **array\<int\>** | ✅ 可能为空数组 | `NormalizedAlertRecord.destination_port` + `AlertRecord.dst_port` | `_first_value()` 取首非空 | 数组取首 → int；全部为空 → None |
| `hostIp` | string | 否（本次非空） | **不直连主字段**（dstIp 回退、_with_raw_context 留存为 `xdr_hostIp`） | 仅当 dstIp 缺失时用作回退 | 无 |
| `threatSubTypeDesc` | string | 否（本次非空） | `NormalizedAlertRecord.event_type` + `AlertRecord.alert_type` | `_xdr_event_type()` 优先级：`threat_sub_type_desc → risk_tag → threat_type_desc → alert_classification → threat_class_desc → name` | 枚举：`sql_injection / webshell / lateral_movement / unauthorized_access / other`；不在字典里的（如"代码注入"、"异常操作"、"SQL注入"等）→ **other** |
| `riskTag` | **array\<string\>** | ✅ 可能为空数组 | 同上，作为 `_xdr_event_type()` 的第二优先级候选 | `_first_text()` 取首元素作为字符串检查 | 空数组 → None → 跳过 |
| `devSourceName` / `engineName` / `devUidDesc` | **array\<string\>** | ✅ 可能为空数组 | `NormalizedAlertRecord.source_device_name` + `AlertRecord.scenario_fields.source_device_name` | `_first_text()` 取首；回退链 `devSourceName → engineName → devUidDesc → "XDR"` | 全部为空数组 → "XDR" 默认值 |

### 2.3 原始字段留存（不进 NormalizedAlertRecord 主字段，由 `_with_raw_context()` 带 `xdr_` 前缀进 scenario_fields）

以下字段全部满足条件才进入 scenario_fields：`value not in (None, "", [], {})`。**空数组/None/空字符串/空对象不入场景字段**，这是正确的数据洁净契约。

| 原始字段 | 类型 | 空值可能 | 留存 key | 说明 |
|---|---|---|---|---|
| `alertRuleId` | string | 否 | `xdr_alertRuleId` | 规则标识 |
| `description` | string | 否 | `xdr_description` | 告警描述 |
| `logCount` | int | 否 | `xdr_logCount` | 聚合日志数 |
| `stage` | int | 否（本次=30） | `xdr_stage` | 平台阶段枚举 |
| `riskTag` | array\<string\> | ✅ 可能空数组 | `xdr_riskTag` | 风险标签（非空时留存） |
| `threatClassDesc` | string | 否 | `xdr_threatClassDesc` | 攻击分类（"数据库攻击利用"/"网站攻击"/"后门通信"） |
| `threatTypeDesc` | string | 否 | `xdr_threatTypeDesc` | 威胁类型（"异常操作"/"代码注入"） |
| `threatSubTypeDesc` | string | 否 | `xdr_threatSubTypeDesc` | 威胁子类（"SQL注入"/"WebShell"） |
| `attckTechnique` | array\<string\> | ✅ 可能空数组 | `xdr_attckTechnique` | ATT&CK 技术（如 "TA0001.T1190"） |
| `threatDefine` | array\<int\> | ✅ 可能空数组 | `xdr_threatDefine` | 威胁定义枚举 |
| `url` | array\<string\> | ✅ 可能空数组 | `xdr_url` | HTTP URL（非空时留存，空数组过滤） |
| `respStatus` | int | 否（本次=200） | `xdr_respStatus` | HTTP 响应状态 |
| `domain` | array\<string\> | ✅ 可能空数组 | — | **空数组不入场景字段**（过滤正确） |
| `xforwardedFor` | array\<string\> | ✅ 可能空数组 | — | **空数组不入场景字段**（过滤正确） |
| `direction` | int | 否（本次=3） | `xdr_direction` | 访问方向枚举 |
| `hostAssetId` | int | 否 | `xdr_hostAssetId` | 资产 ID |
| `branchName` | string | 否 | `xdr_branchName` | 管理范围/分支 |
| `devUidDesc` | array\<string\> | ✅ 可能空数组 | `xdr_devUidDesc` | 平台来源设备（如 ["NDR"]） |
| `engineName` | array\<string\> | ✅ 可能空数组 | `xdr_engineName` | 检测引擎（如 ["PVS引擎"]） |
| `devSourceName` | array\<string\> | ✅ 可能空数组 | `xdr_devSourceName` | 告警来源设备（如 ["STA (REDACTED)"]） |
| `gptResult` | int | 否（本次=110） | `xdr_gptResult` | GPT 研判枚举 |
| `gptResultDescription` | string | 否 | `xdr_gptResultDescription` | GPT 研判文字（"真实攻击成功"/"疑似攻击行为"/"误报"） |
| `attackState` | int | 否（本次=0 或 2） | `xdr_attackState` | 攻击状态枚举（合法值 `0` 保留，非 `None/""/[]/{}`） |
| `confidence` | int | 否（本次=20） | `xdr_confidence` | 平台置信度 |
| `alertDealStatus` | int | 否（本次=1） | `xdr_alertDealStatus` | 处置状态枚举 |
| `alertDealAction` | string | 否（本次="待处置"） | `xdr_alertDealAction` | 处置动作文字 |
| `whiteStatus` | string | 否（本次="未加白"） | `xdr_whiteStatus` | 加白状态 |
| `firstTime` | int | 否 | `xdr_firstTime` | 首次发生（Unix 秒戳，留存原始值） |
| `lastTime` | int | 否 | `xdr_lastTime` | 最后发生 |
| `updateTime` | int | 否 | `xdr_updateTime` | 更新时间 |

### 2.4 **不入场景字段**（当前代码刻意过滤）

| 原始字段 | 类型 | 空值形式 | 过滤原因 |
|---|---|---|---|
| `pname` | null | null | `None in (None,"",[],{})` → 过滤 |
| `fileMd5` | null | null | 同上 |
| `exploitCveId` | null | null | 同上 |
| `srcIpInfos` | array\<object\> | 可能存在 | 不在 `_with_raw_context` 30 字段白名单里 → 不过滤也不留存 |
| `dstIpInfos` | array\<object\> | 可能存在 | 同上 |
| `hostGroupIds` | array | 空数组 `[]` | `[] in (None,"",[],{})` → 过滤 |
| `hostGroups` | array | 空数组 `[]` | 同上 |

### 2.5 `traceBackId` → EvidenceRef 契约

| 官方字段 | 类型 | 空值可能 | 映射目标 | 说明 |
|---|---|---|---|---|
| `traceBackId` | **array\<string\>** | ✅ 可能为空数组 | `AlertRecord.evidence_refs`（追加 `kind="xdr_traceback"` 的 EvidenceRef） | 仅当 `isinstance(traceBackId, list)` 时追加；空数组或非 list → 跳过，不伪造证据 |

---

## 3. 四模型逐字段总览

### 3.1 XdrOpenApiConfig（输入侧）

| 字段 | 类型 | 默认 | 必填 | 说明 |
|---|---|---|---|---|
| `base_url` | str \| None | None | 是（xdr_openapi 后端） | XDR 服务地址 |
| `auth_type` | `"token"\|"aksk"\|"auth_code"` | `"token"` | 是 | 鉴权模式 |
| `token` / `access_key`+`secret_key` / `auth_code` | str \| None | None | 按 auth_type | 凭据 |
| `alerts_path` | str | `"/api/xdr/v1/alerts/list"` | — | ✅ 官方真实路径 |
| `logs_path` | str | `"/api/v1/logs"` | — | — |
| `alert_page_size` | int | 50 | — | ✅ 官方分页默认 |
| `alert_max_pages` | int | 20 | — | 防御上限 |
| `alert_start_timestamp` | int \| None | None | — | 历史查询起点 |
| `verify_ssl` | bool | False | — | ✅ 官方真实环境证书 |

### 3.2 NormalizedAlertRecord（标准化中间模型）

| 字段 | 类型 | 必填 | 枚举 | 来源（PR33 主链） |
|---|---|---|---|---|
| `event_id` | str | ✅ | — | uuId → sample_id |
| `event_time` | datetime(tz-aware) | ✅ | — | lastTime → firstTime → updateTime 优先链 |
| `source_device_type` | `"XDR"` | ✅ | 固定 | — |
| `source_device_name` | str \| None | — | — | devSourceName / engineName / devUidDesc / "XDR" |
| `event_type` | `"sql_injection"\|"webshell"\|"lateral_movement"\|"unauthorized_access"\|"other"` | ✅ | 枚举 | threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name |
| `rule_or_event_name` | str | ✅ | — | name（官方字段） |
| `severity` | `"critical"\|"high"\|"medium"\|"low"` | ✅ | 枚举 | 数字 50/70/90+ / 中文映射双路径 |
| `source_ip` | str \| None | — | — | srcIp[] 取首 |
| `source_port` | int(0-65535) \| None | — | int,0-65535 | srcPort[] 取首 |
| `destination_ip` | str \| None | — | — | dstIp[] 取首 → 回退 hostIp |
| `destination_port` | int(0-65535) \| None | — | int,0-65535 | dstPort[] 取首 |
| `transport_protocol` | str \| None | — | — | 有 srcPort 则 "tcp" |
| `application_protocol` | str \| None | — | — | 按 event_type 派生（sql_injection/webshell→http, lateral→smb） |
| `affected_asset` | str \| None | — | — | = destination_ip（mapping.csv 规则 16/23-26） |
| `evidence_source` | str | ✅ | — | "xdr_security_alert"（sample_source="XDR 安全告警分析" 映射） |
| `evidence_refs` | list\<str\> | — | — | _XDR_EVIDENCE_FIELDS 里的真实字段名 |
| `sample_nature` | `"platform_derived"\|"synthetic_regression"` | ✅ | 枚举 | 固定 "platform_derived" |
| `status` | `"new"` | ✅ | 枚举 | 固定 "new" |
| `risk_score_seed` | int(0-100) | — | int,0-100 | severity→critical:90/high:80/medium:65/low:30（蚁剑专项 95） |
| `investigation_hint` | str \| None | — | — | 按 event_type 映射固定提示文案 |
| `recommended_action` | str \| None | — | — | 按 event_type 映射固定处置建议 |

### 3.3 AlertRecord（主链消费模型）

| 字段 | 类型 | 来源 |
|---|---|---|
| `alert_id` | str | NormalizedAlertRecord.event_id |
| `source` | `"xdr_openapi"` | 固定 |
| `occurred_at` | datetime(tz-aware) | NormalizedAlertRecord.event_time |
| `name` | str | NormalizedAlertRecord.rule_or_event_name |
| `alert_type` | str | NormalizedAlertRecord.event_type |
| `raw_severity` | str | NormalizedAlertRecord.severity |
| `src_ip` / `dst_ip` | str \| None | NormalizedAlertRecord.source_ip / destination_ip |
| `src_port` / `dst_port` | int \| None | NormalizedAlertRecord.source_port / destination_port |
| `assets` | list\<str\> | `[affected_asset]`，空则 `[]` |
| `attack_status` | str \| None | NormalizedAlertRecord.status（"new"） |
| `scenario_fields` | dict（30+个 xdr_* 原始字段 + 标准化扩展字段） | 由 `_with_raw_context()` 注入 + `_from_normalized()` 构造 |
| `evidence_refs` | list\<EvidenceRef\> | 标准化字段引用 + traceBackId 追加 |
| `raw_record_ref` | str | `"xdr://openapi/alerts#{uuId}"` |

### 3.4 SecurityEvent（关联压缩模型）

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | str | `"evt-{uuid4()}"` 自动生成 |
| `alert_refs` | list\<str\> | 按时间排序后的 alert.alert_id 列表 |
| `first_seen_at` / `last_seen_at` | datetime | 告警时间窗口两端 |
| `entities` | dict | `src_ips` / `dst_ips` / `assets` / `source_devices` 四个去重集合 |
| `correlation_reason` | str | 自动生成的关联依据描述 |
| `alert_count_before` / `event_count_after` | int | 压缩前后数量（N→1） |
| `summary` | str | 压缩摘要 |

---

## 4. 时间与时区规则

| 环节 | 行为 |
|---|---|
| 原始字段 | 官方 `firstTime`/`lastTime`/`updateTime` 是 **Unix 秒戳（int）** |
| `_time_to_text()` | int → `datetime.fromtimestamp(timestamp)` **使用本地墙钟** → `.isoformat()` |
| `RawJsonlNormalizer._parse_time()` | 无时区时补 `Asia/Shanghai`；已有时区保留 |
| `AlertRecord.occurred_at` | 最终带时区（+08:00） |
| ⚠️ 部署假设 | `datetime.fromtimestamp()` 取墙钟，隐含 **Python 服务器时区 = Asia/Shanghai** |

---

## 5. 证据缺口

| 缺口 | 影响 | 严重度 |
|---|---|---|
| severity 数字→专项升级的映射语义未统一 | 蚁剑 WebShell 真实 severity=70 永远是 high/80，固定样例演示走 critical/95 | ⚠️ 中：同一告警在两条路径分级不一致（固定样例→critical，真实→high） |
| 部署时区假设未写入文档 | 非 Asia/Shanghai 墙钟部署会发生 occurred_at 偏差 | ⚠️ 中：环境依赖隐式 |
| `NormalizedAlertRecord.model_validate()` 首路径的直接 schema 匹配 | 官方脱敏结构字段全为 camelCase，大概率走第二条 raw→normalizer 路径；第一条为兼容旧 JSONL 固定样例保留 | ℹ️ 低：代码冗余 |

---

## 6. 版本
`2026-09-03.t0903-chenmin-v1`
