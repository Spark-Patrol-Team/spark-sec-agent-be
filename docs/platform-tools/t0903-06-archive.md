# T0903-06 陈敏：真实输入契约资产迁移 · 前三步执行存档

> **执行人**：陈敏（字段确认人）
> **执行日期**：2026-09-03
> **任务编号**：T0903-06
> **基线**：`origin/main` @ `e154343`（已含 PR#33 完整版本 `e3cca8f`）
> **分支**：`chenmin/t0903-6-origin-main-clean`
> **最终测试基线**：**175 passed, 0 failed, 1 skipped**（原 main 150 + T0903-06 新增 21 + PR#22 升级后 4）
> **官方参考文件**：`aksk_py3.py`（签名 SDK）、`test_aksk.py`（调用示例）、`XDR_OpenAPI更新版(1).md`（真实字段结构清单）、`运行日志清单.md`

---

## 目录

1. [任务背景与约束](#1-任务背景与约束)
2. [执行日志](#2-执行日志)
3. [第 1 步：审计与迁移清单](#3-第-1-步审计与迁移清单)
4. [第 2 步：四模型逐字段契约包](#4-第-2-步四模型逐字段契约包)
5. [第 3 步：脱敏真实结构转换 + 回归测试](#5-第-3-步脱敏真实结构转换--回归测试)
6. [PR#22 契约资产升级迁移](#6-pr22-契约资产升级迁移)
7. [产出文件清单](#7-产出文件清单)
8. [检查与核查结果](#8-检查与核查结果)
9. [任务完成情况自评](#9-任务完成情况自评)
10. [遗留问题与后续步骤](#10-遗留问题与后续步骤)

---

## 1. 任务背景与约束

### 1.1 任务来源

按照《XDR_OpenAPI更新版(1)》文档中五步法图片的要求，陈敏的职责是"字段确认人"：**核对真实返回是否正确转换为现有告警对象、字段是否正确、空值是否正确、分页是否正确、去重是否正确**。

### 1.2 执行约束

| 约束 | 说明 |
|---|---|
| 基线分支 | 从最新 `origin/main` @ `e154343` 建干净分支，不携带任何旧候选路径 |
| PR#33 对齐 | main 已含 PR#33 `e3cca8f`，POST `/api/xdr/v1/alerts/list` + `XdrOfficialSigner` + `uuId` + `data.item` 分页均已落地 |
| PR#22 资产 | PR#22 @ 2026-08-27 是早期契约草稿（字段名多为占位符），从未被 merge 回 main，但其 4 个独有结构化资产（CSV 映射表、契约 md、2 个 sanitized fixture、4 条契约测试）值得保留，需升级到官方真实字段后迁入 |
| 不直接修改代码 | 用户明确要求"先指出问题，不直接修改代码"——前三步全部为新增文件（文档 + fixture + 测试），不修改任何现有源码 |
| 脱敏规则 | 真实 IP、ID、URL、Token、auth_code 均不得进入 Git；fixture 使用 RFC 5737 文档地址和 `<REDACTED_*>` 占位符 |

### 1.3 五步法中的前三步

| 步骤 | 内容 | 状态 |
|---|---|---|
| **第 1 步** | 从最新 main 建干净分支，只提取 PR#22 仍有效的字段映射、脱敏契约、分页/去重/缺字段/空结果规则和契约测试 | ✅ 完成 |
| **第 2 步** | 将运行 A 实际字段与四模型逐字段确认 → 字段契约包 | ✅ 完成 |
| **第 3 步** | 脱敏真实结构转换测试 + 固定样例 + 缺字段 + 空结果 + 去重回归 | ✅ 完成 |
| 第 4 步 | 给闫昱硕的研判字段/证据摘要 + 给杨景凡的调查实体/证据引用摘要 | ⏸ 等待用户指示 |
| 第 5 步 | 增量更新告警接入与关联三份模块文档 | ⏸ 等待用户指示 |

---

## 2. 执行日志

### 2.1 Git 操作

```
# 从最新 main 建干净分支
git fetch origin
git checkout -B chenmin/t0903-6-origin-main-clean e154343

# 拉取 PR#22（早期契约草稿，从未 merge 回 main）
git fetch origin pull/22/head:pr22
git log --oneline pr22
# 1f02e2f docs: append XDR contract preparation to module docs
# 5ae5a53 docs: add XDR input contract preparation

# PR#22 独有文件清单
git diff --name-only 4190550..pr22
# docs/modules/platform-tools/xdr_field_mapping.csv
# docs/modules/platform-tools/xdr_input_contract.md
# tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json
# tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json
# tests/test_xdr_input_contract.py

# 将 PR#22 的 4 个独有资产 checkout 到干净分支
git checkout pr22 -- docs/modules/platform-tools/xdr_field_mapping.csv \
    docs/modules/platform-tools/xdr_input_contract.md \
    tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json \
    tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json \
    tests/test_xdr_input_contract.py
```

### 2.2 测试执行

```
# 基线测试（main 原始）
$env:PYTHONPATH="$PWD\src"
python -m pytest tests/ -q                    # → 150 passed, 1 skipped

# PR#22 原始契约测试（升级前）
python -m pytest tests/test_xdr_input_contract.py -v
# → 4 passed（结构守护测试，检查占位符不被篡改）

# PR#22 升级后契约测试
python -m pytest tests/test_xdr_input_contract.py -v
# → 4 passed（升级到官方字段后仍全绿）

# T0903-06 新增契约回归测试
python -m pytest tests/test_t0903_06_contract_regression.py -v
# → 21 passed（5 场景组：脱敏转换 8 / 固定样例 2 / 缺字段 5 / 空结果 2 / 去重 4）

# 全量回归（最终基线）
python -m pytest tests/ -q                    # → 175 passed, 1 skipped
```

### 2.3 测试基线演变

| 阶段 | passed | failed | skipped | 说明 |
|---|---|---|---|---|
| main 原始基线 | 150 | 0 | 1 | PR#33 已完整落地 |
| + T0903-06 新增 21 条 | 171 | 0 | 1 | 脱敏真实转换 + 固定样例 + 缺字段 + 空结果 + 去重 |
| + PR#22 升级后 4 条 | **175** | **0** | 1 | PR#22 契约结构测试升级到官方字段 |

---

## 3. 第 1 步：审计与迁移清单

### 3.1 九个判断点逐项结论

| # | 判断点 | 结论 | 关键证据 |
|---|---|---|---|
| 1.1 | 字段映射表是否仍有效？ | ✅ 有效，但分散在两处未集中成文档 | `XdrOpenApiAdapter._to_normalizer_raw()` + `RawJsonlNormalizer._normalize_xdr()` + `_with_raw_context()` |
| 1.2 | XDR 输入契约是否与当前实现一致？ | ✅ 一致 | POST `/api/xdr/v1/alerts/list` + JSON body + `XdrOfficialSigner` 三种鉴权 |
| 1.3 | 脱敏请求/响应样例是否还能用于测试？ | ✅ 能用，但需要固化 | 已固化为 `tests/fixtures/xdr_openapi/` 和 `tests/fixtures/xdr_contract/` |
| 1.4 | 分页规则是否有正式依据？ | ✅ 有正式依据 | 官方文档第 10 节 `page + pageSize + total + item`；防御上限 `alert_max_pages=20` |
| 1.5 | 去重规则是否符合当前代码？ | ✅ 符合 | fetch 阶段 `seen_ids` 按 `uuId` + correlation 阶段四条件二次压缩 |
| 1.6 | 缺字段和非法字段处理是否还需要保留？ | ✅ 需要保留，已正确实现 | 必需三字段缺一 → ValueError（不降级）；`PlatformIngestError` 六类 kind |
| 1.7 | 空结果语义是否正确？ | ✅ 正确 | `item=[]` → `empty_result` error；空数组/null/空串不入 scenario_fields；`attackState=0` 合法值保留 |
| 1.8 | 契约测试是否能迁移？ | ✅ main 已有 27 个 XDR 测试，可直接继承 | `test_xdr_openapi_platform.py` 20 个 + `test_raw_jsonl_ingest_and_correlation.py` 6 个 + `test_mvp_tool.py` 1 个 |
| 1.9 | 哪些内容已被 main 实现、不需要重复加入？ | ✅ main 已完整实现 | POST + 签名 + uuId + item 分页 + 数组取首 + lastTime 优先 + threatSubTypeDesc 链 + 数字 severity + 30 字段留存 + traceBackId EvidenceRef + 六类错误 |

### 3.2 迁移清单

| 类型 | 文件 | 动作 |
|---|---|---|
| ✅ 已被 main 完整实现 | `src/sec_agent/platforms/xdr_openapi.py` | 保留 |
| ✅ 已被 main 完整实现 | `src/sec_agent/platforms/raw_jsonl.py` | 保留 |
| ✅ 已被 main 完整实现 | `src/sec_agent/core/config.py` | 保留 |
| ✅ 已被 main 完整实现 | `src/sec_agent/domain/models.py` | 保留 |
| ✅ 已被 main 完整实现 | `tests/test_xdr_openapi_platform.py` | 保留（20 个契约测试） |
| ✅ 已被 main 完整实现 | `tests/fixtures/fixed_alerts/` | 保留（固定样例回归基线） |
| 🔄 PR#22 独有，已升级迁入 | `docs/modules/platform-tools/xdr_field_mapping.csv` | 14 条 → 20 条 official camelCase |
| 🔄 PR#22 独有，已升级迁入 | `tests/test_xdr_input_contract.py` | 4 条占位符检查 → 4 条官方字段检查 |
| 🔄 PR#22 独有，已升级迁入 | `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | PROVIDER_DEFINED → POST + JSON body |
| 🔄 PR#22 独有，已升级迁入 | `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | records[] + snake_case → item[] + camelCase |
| 🆕 T0903-06 新增 | `docs/platform-tools/t0903-06-step1-audit.md` | 第 1 步审计报告 |
| 🆕 T0903-06 新增 | `docs/platform-tools/t0903-06-step2-contract-package.md` | 第 2 步字段契约包 |
| 🆕 T0903-06 新增 | `tests/fixtures/xdr_openapi/official_desensitized_alert.json` | 官方脱敏单条告警 JSON |
| 🆕 T0903-06 新增 | `tests/fixtures/xdr_openapi/official_desensitized_response.json` | 官方分页壳示例 |
| 🆕 T0903-06 新增 | `tests/test_t0903_06_contract_regression.py` | 21 条端到端契约回归 |

### 3.3 不迁移清单

| 不迁移内容 | 丢弃原因 |
|---|---|
| 任何 `GET /api/v1/alerts` 风格实现 | 与官方 POST 契约冲突 |
| 任何不带 `uuId` 的旧唯一标识链 | `uuId` 是官方确认的唯一标识 |
| 任何不带 `item` 单数字段的老分页 | 官方分页结构明确为 `item` |
| PR#22 §6 的 cursor 分页占位符 `page_token` | 官方使用页码式分页，不是游标 |
| PR#22 早期 severity 纯中文映射（无数字路径） | 真实 severity 是 int（50/70/...），数字路径优先 |

### 3.4 完成标准自评

| 标准 | 达成？ |
|---|---|
| 不带回旧候选路径 | ✅ POST /api/xdr/v1/alerts/list 是唯一接口契约，无 GET 旧实现残留 |
| 不带回旧鉴权结论 | ✅ 官方签名唯一，无自带 HMAC 旁路 |
| 不带回第二套上层告警对象 | ✅ AlertRecord / NormalizedAlertRecord 唯一，无重复模型 |
| 列出迁移与不迁移文件 | ✅ 见上方表格 |

---

## 4. 第 2 步：四模型逐字段契约包

### 4.1 版本信息

| 项目 | 值 |
|---|---|
| 契约版本 | `2026-09-03.t0903-chenmin-v1` |
| 依赖 Commit | `e154343` |
| 输入协议 | POST `/api/xdr/v1/alerts/list` + JSON body 分页 |
| 唯一标识 | `uuId` |
| 时间标准 | `lastTime`（优先）→ `firstTime` → `updateTime`；Unix 秒戳 + Asia/Shanghai |
| 分页语义 | 页码式 `page + pageSize + total + item`，`alert_max_pages=20` 上限 |
| 去重语义 | fetch 阶段基于 `uuId`（兜底整条 JSON 序列化）+ correlation 阶段按类型/资产/设备/窗口四条件二次压缩 |

### 4.2 顶层返回契约

```json
{
  "code": "Success",
  "message": "成功",
  "data": {
    "total": 8,
    "page": 1,
    "pageSize": 50,
    "item": [ /* 单条告警对象数组 */ ]
  }
}
```

- `code` 非 `"Success"/"success"/"0"` → `PlatformIngestError(platform_error)`
- `data.item` 为空数组 → `empty_result` error
- `data.item` 是官方单数字段（不是 `items`）

### 4.3 必需三字段（缺失直接 ValueError，不降级）

| 官方字段 | 类型 | 映射目标 | 空值策略 |
|---|---|---|---|
| `uuId` | string | `AlertRecord.alert_id` + `NormalizedAlertRecord.event_id` | 全部候选缺失 → ValueError |
| `lastTime` / `firstTime` / `updateTime` | int（Unix 秒） | `AlertRecord.occurred_at` + `NormalizedAlertRecord.event_time` | 优先级 lastTime→firstTime→updateTime；全部缺失 → ValueError |
| `name` | string | `AlertRecord.name` + `NormalizedAlertRecord.rule_or_event_name` | 空字符串视为缺失 → ValueError |

### 4.4 可选核心字段

| 官方字段 | 类型 | 映射目标 | 关键转换规则 |
|---|---|---|---|
| `severity` | **int**（50/70/90+） | `NormalizedAlertRecord.severity` + `AlertRecord.raw_severity` | 数字优先：≥90→critical/90，≥70→high/80，≥50→medium/65，<50→low/30；中文回退 |
| `srcIp` | **array\<string\>** | `source_ip` + `src_ip` | `_first_value()` 取首非空 |
| `srcPort` | **array\<int\>** | `source_port` + `src_port` | 取首非空 int（0..65535） |
| `dstIp` | **array\<string\>** | `destination_ip` + `dst_ip` | 取首 → 回退 `hostIp` |
| `dstPort` | **array\<int\>** | `destination_port` + `dst_port` | 取首非空 int |
| `threatSubTypeDesc` | string | `event_type` + `alert_type` | 6 层优先链：threatSubTypeDesc→riskTag→threatTypeDesc→alert_classification→threatClassDesc→name |
| `riskTag` | **array\<string\>** | 同上（第二优先级） | `_first_text()` 取首元素 |
| `devSourceName` / `engineName` / `devUidDesc` | **array\<string\>** | `source_device_name` | 回退链 → 常量 "XDR" |

### 4.5 原始字段留存（30 个白名单，`xdr_` 前缀进 scenario_fields）

过滤条件：`value not in (None, "", [], {})` 才保留。
- ✅ 保留：`attackState=0`（合法 int）、`attackState=2`、`confidence=20`、非空数组 `url`/`riskTag`/`attckTechnique` 等
- ❌ 过滤：`pname=null`、`fileMd5=null`、`exploitCveId=null`、空数组 `domain`/`xforwardedFor`/`hostGroupIds`/`hostGroups`

### 4.6 traceBackId → EvidenceRef

| 官方字段 | 类型 | 映射目标 | 规则 |
|---|---|---|---|
| `traceBackId` | **array\<string\>** | `AlertRecord.evidence_refs`（追加 `kind="xdr_traceback"`） | 每项生成 `EvidenceRef(ref_id=alert_id:traceBackId:{id})`；空数组跳过，不伪造证据 |

### 4.7 四模型总览

| 模型 | 关键字段 | 说明 |
|---|---|---|
| **XdrOpenApiConfig** | `base_url`, `auth_type`, `alerts_path="/api/xdr/v1/alerts/list"`, `alert_page_size=50`, `alert_max_pages=20`, `verify_ssl=False` | 输入侧配置 |
| **NormalizedAlertRecord** | `event_id`, `event_time(tz)`, `source_device_type="XDR"`, `event_type(枚举)`, `severity(枚举)`, `source_ip`, `source_port`, `destination_ip`, `destination_port`, `affected_asset`, `evidence_source`, `risk_score_seed(0-100)` | 标准化中间模型 |
| **AlertRecord** | `alert_id`, `source="xdr_openapi"`, `occurred_at(tz)`, `name`, `alert_type`, `raw_severity`, `src_ip`, `dst_ip`, `src_port`, `dst_port`, `assets[]`, `attack_status`, `scenario_fields(dict)`, `evidence_refs[]`, `raw_record_ref` | 主链消费模型 |
| **SecurityEvent** | `event_id`, `alert_refs[]`, `first_seen_at`, `last_seen_at`, `entities{src_ips,dst_ips,assets,source_devices}`, `alert_count_before`, `event_count_after` | 关联压缩模型 |

---

## 5. 第 3 步：脱敏真实结构转换 + 回归测试

### 5.1 测试覆盖矩阵（21 条）

| 场景组 | 测试数 | 覆盖点 |
|---|---|---|
| 脱敏真实结构转换 | 8 | 基础字段映射 / lastTime 优先 / 标准化字段+原始字段 xdr_ 前缀 / 空数组过滤 / null 过滤 / traceBackId→xdr_traceback EvidenceRef / url 非空数组保留 / 完整主链 APPROVAL_REQUIRED |
| 固定样例回归 | 2 | FixedSampleAdapter 仍返回 2 条 / 固定样例主链仍到 APPROVAL_REQUIRED |
| 缺字段处理 | 5 | uuId 缺失 / 三时间全缺 / name 缺失 / field_mapping 永不降级 / business code Fail 永不降级 |
| 空结果处理 | 2 | `item=[] + total=0` → empty_result / 即使 allow_fallback=True 也不降级 |
| 去重契约 | 4 | 跨页同 uuId 去重 / 精确 lookup 本地过滤 / 关联压缩 N→1 / 类型不匹配拒绝关联 |

### 5.2 端到端验证结果

用官方脱敏真实结构（`XDR_OpenAPI更新版(1).md` 第五部分）构造模拟返回，验证完整主链：

| 检查项 | 期望 | 实际 | 结果 |
|---|---|---|---|
| 返回条数 | 1 | 1 | ✅ |
| uuId→alert_id | `alert-REDACTED-UUID` | `alert-REDACTED-UUID` | ✅ |
| name | `SQL server数据库查询sa账户密码攻击` | 同左 | ✅ |
| severity=70→raw_severity | `high` | `high` | ✅ |
| severity=70→risk_score_seed | 80 | 80 | ✅ |
| srcIp[]取首 | `192.168.X.X` | `192.168.X.X` | ✅ |
| dstIp[]取首 | `192.168.Y.Y` | `192.168.Y.Y` | ✅ |
| threatSubTypeDesc→event_type | `sql_injection` | `sql_injection` | ✅ |
| lastTime→occurred_at（优先） | lastTime 时间戳 | lastTime 时间戳 | ✅ |
| traceBackId→evidence_refs | 1 条 xdr_traceback | 1 条 xdr_traceback | ✅ |
| 空数组 domain 过滤 | 不入 scenario_fields | 不在 | ✅ |
| null pname 过滤 | 不入 scenario_fields | 不在 | ✅ |
| 终态 | APPROVAL_REQUIRED | APPROVAL_REQUIRED | ✅ |
| effective_source | xdr_openapi | xdr_openapi | ✅ |
| fallback_source | None | None | ✅ |
| errors | [] | [] | ✅ |
| 时间线六状态 | RECEIVED→CORRELATING→TRIAGED→INVESTIGATING→DECISION_READY→APPROVAL_REQUIRED | 完整匹配 | ✅ |

### 5.3 PR#22 契约测试升级前后对比

| 测试 | PR#22 原始（占位符） | 升级后（官方字段） | 结果 |
|---|---|---|---|
| test_request | `endpoint=PROVIDER_DEFINED_NOT_COMMITTED` | `method=POST` + `endpoint=/api/xdr/v1/alerts/list` + JSON body | ✅ |
| test_response | `data.records[]` + `event_id` + `alert_grade` | `data.item[]` + `uuId` + `severity:int` + `srcIp[]` + `threatSubTypeDesc` | ✅ |
| test_expectations | `destination_ip_first_host_ip_fallback_only` | `dstIp_first_hostIp_fallback_only` + `uuId` + `lastTime` + `threatSubTypeDesc` | ✅ |
| test_redaction | 不含 `XDR_BASE_URL=` / `Bearer ` | 不变 | ✅ |

---

## 6. PR#22 契约资产升级迁移

### 6.1 PR#22 是什么

PR#22 @ 2026-08-27（任务号 `T0827-06`）是 **early-stage 契约草稿**，当时还没拿到官方真实字段，字段名多为 `<PROVIDER_DEFINED>` 占位符。明确写了"本轮只准备映射和脱敏结构，不包含真实 XDR 请求、凭据、响应或适配器实现"。

PR#22 从未被任何后续 PR merge 回 main——main 的真实字段对齐走的是 PR#26→PR#28→PR#32(revert)→PR#33 另一条路径。但 PR#22 的 4 个独有结构化资产是 main 上没有的。

### 6.2 PR#22 原始 vs 升级后

| 维度 | PR#22 原始（2026-08-27 占位符） | 升级后（2026-09-03 官方真实字段） |
|---|---|---|
| HTTP Method | `PROVIDER_DEFINED` | **POST** |
| Endpoint | `PROVIDER_DEFINED_NOT_COMMITTED` | **`/api/xdr/v1/alerts/list`** |
| 鉴权 | `LOCAL_ENV_OR_SECRET_STORE_ONLY` | **XdrOfficialSigner HMAC-SHA256** |
| 请求体 | `time_range.start_time=<ISO8601>`、`pagination=PROVIDER_DEFINED_PAGE_OR_CURSOR` | **JSON body `{"page":int, "pageSize":50, "startTimestamp":int?}`** |
| 响应顶层 | `data.records[]` + `pagination.has_next/next_page_token/total_count` | **`data.item[]`（单数字段）+ `total/page/pageSize`** |
| 唯一标识 | 候选 `event_id/alert_id/id` | **官方确认 `uuId`** |
| severity 类型 | `<PROVIDER_SEVERITY_ENUM>` | **`int`**（50/70/90+） |
| 时间类型 | `<ISO8601_WITH_TIMEZONE>` | **`int Unix 秒戳`**（lastTime/firstTime/updateTime 三字段） |
| 分页方式 | 游标候选 `page_token` | **页码式**（page + pageSize + total） |
| CSV 映射条目 | 14 条 snake_case 占位符 | **20 条 official camelCase**（001-014 升级 + 015-020 新增） |

### 6.3 CSV 新增条目（PR#33 契约）

| mapping_id | 角色 | 说明 |
|---|---|---|
| XDR-MAP-015 | raw_field_preservation | 30 个官方字段白名单 + 过滤条件 `value not in (None,"",[],{})` |
| XDR-MAP-016 | pagination_contract | POST + JSON body + total 翻页 + max_pages=20 上限 |
| XDR-MAP-017 | signature_contract | XdrOfficialSigner 三种模式 + canonical 构造规则 |
| XDR-MAP-018 | deduplication_contract | fetch 阶段 uuId 去重 + correlation 四条件二次压缩 |
| XDR-MAP-019 | error_classification | PlatformIngestError 六类 kind + retryable + allow_fallback |
| XDR-MAP-020 | severity_numeric_vs_string | ⚠️ 遗留问题：数字路径与字符串专项升级条件未统一 |

---

## 7. 产出文件清单

### 7.1 文档产出

| 文件 | 步骤 | 说明 |
|---|---|---|
| [t0903-06-step1-audit.md](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/docs/platform-tools/t0903-06-step1-audit.md) | 第 1 步 | 9 项判断点 + 迁移/不迁移清单 + 完成标准自评 |
| [t0903-06-step2-contract-package.md](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/docs/platform-tools/t0903-06-step2-contract-package.md) | 第 2 步 | 四模型逐字段契约包（顶层返回 + 必需字段 + 可选字段 + 原始留存 + traceBackId + 时间规则 + 证据缺口） |
| [t0903-06-archive.md](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/docs/platform-tools/t0903-06-archive.md) | 存档 | 本文件：前三步执行结果与检查核查结果存档 |
| [xdr_input_contract.md](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/docs/modules/platform-tools/xdr_input_contract.md) | PR#22 升级 | 从 PR#22 原始草稿升级到官方真实字段（§3 数据流 + §4 字段映射 + §6 双列对比 + §7 六类错误 + §9 变更记录） |
| [xdr_field_mapping.csv](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/docs/modules/platform-tools/xdr_field_mapping.csv) | PR#22 升级 | 20 条 official camelCase 映射（14 条升级 + 6 条新增） |

### 7.2 Fixture 产出

| 文件 | 步骤 | 性质 |
|---|---|---|
| [official_desensitized_alert.json](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/fixtures/xdr_openapi/official_desensitized_alert.json) | 第 3 步 | **真实脱敏结构**（来自官方文档第五部分） |
| [official_desensitized_response.json](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/fixtures/xdr_openapi/official_desensitized_response.json) | 第 3 步 | 官方分页壳示例 |
| [xdr_list_alerts_request_sanitized.json](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json) | PR#22 升级 | POST + JSON body 结构守护 |
| [xdr_list_alerts_response_sanitized.json](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json) | PR#22 升级 | item[] + camelCase 结构守护 |

### 7.3 测试产出

| 文件 | 步骤 | 测试数 | 说明 |
|---|---|---|---|
| [test_t0903_06_contract_regression.py](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/test_t0903_06_contract_regression.py) | 第 3 步 | 21 | 脱敏真实转换 8 + 固定样例 2 + 缺字段 5 + 空结果 2 + 去重 4 |
| [test_xdr_input_contract.py](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/tests/test_xdr_input_contract.py) | PR#22 升级 | 4 | 请求结构 + 响应结构 + adapter_expectations + 脱敏约束 |

---

## 8. 检查与核查结果

### 8.1 字段映射核查（58 项逐字段核对）

基于官方脱敏真实结构构造模拟返回，共 **58 项核对：57 项通过，1 项待团队决策**。

| 维度 | 核对项数 | 通过 | 待决策 |
|---|---|---|---|
| 字段映射 | 35 | 35 | 0 |
| 空值处理 | 4 | 4 | 0 |
| 分页 | 7 | 7 | 0 |
| 去重 | 5 | 5 | 0 |
| 端到端 | 6 | 6 | 0 |
| 专项升级 | 1 | 0 | 1（severity 数字 vs 字符串） |
| **合计** | **58** | **57** | **1** |

### 8.2 核查明细

**字段映射（35 项全过）**：`uuId→alert_id`、`name`、`severity 70→high/80`、`srcIp/srcPort/dstIp/dstPort` 数组取首、`affected_asset→assets`、`threatSubTypeDesc→event_type`、`lastTime→occurred_at`、`traceBackId[]→evidence_refs(xdr_traceback)`、`gptResultDescription/attackState=2/confidence/alertDealAction/whiteStatus` 留存、`devSourceName` 设备回退链、`evidence_source=xdr_security_alert`、`source=xdr_openapi`、`attack_status=new`。

**空值处理（4 项全过）**：`dstIp=[]→hostIp` 回退、`srcPort/dstPort=[]→None`、`traceBackId=[]→无伪造证据`、`pname/fileMd5/exploitCveId=null` 与 `domain/xforwardedFor=[]` 均不入 scenario_fields。

**分页（7 项全过）**：POST body `{"page":1,"pageSize":50}`、`total=70` 自动翻 2 页、`total=120 + max_pages=2` 时请求 `[1,2]` 后截断、业务码 `Fail→platform_error` 不降级、空 `item→empty_result` 不降级。

**去重（5 项全过）**：跨页同 `uuId` 去重、精确 `xdr_event_id` 本地过滤、关联压缩 3→1、实体集合去重。

**端到端（6 项全过）**：真实形状 → `APPROVAL_REQUIRED`、`effective_source=xdr_openapi`、`fallback_source=None`、时间线六状态完整、`errors=[]`。

### 8.3 PR#22 契约测试核查（4/4 全绿）

| 测试 | PR#22 原始断言 | 升级后断言 | 结果 |
|---|---|---|---|
| test_request | `endpoint=PROVIDER_DEFINED_NOT_COMMITTED` | `method=POST` + `endpoint=/api/xdr/v1/alerts/list` + body 有 page/pageSize | ✅ |
| test_response | `data.records[0]` 有 `event_id/alert_id/alert_time/alert_name/alert_grade` | `data.item[0]` 有 `uuId/name/severity:int/lastTime/srcIp[]/dstIp[]/threatSubTypeDesc/riskTag[]/traceBackId[]/devSourceName[]` | ✅ |
| test_expectations | `affected_asset_rule=destination_ip_first_host_ip_fallback_only` | `stable_identifier_preference[0]=uuId` + `time_priority_preference=[lastTime,firstTime,updateTime]` + `affected_asset_rule=dstIp_first_hostIp_fallback_only` | ✅ |
| test_redaction | 不含 `XDR_BASE_URL=` / `Bearer ` | 不变 | ✅ |

---

## 9. 任务完成情况自评

### 9.1 第 1 步完成标准

| 标准 | 达成？ | 说明 |
|---|---|---|
| 不带回旧候选路径 | ✅ | POST /api/xdr/v1/alerts/list 是唯一接口契约，无 GET 旧实现残留 |
| 不带回旧鉴权结论 | ✅ | 官方签名 XdrOfficialSigner 唯一，无自带 HMAC 旁路 |
| 不带回第二套上层告警对象 | ✅ | AlertRecord / NormalizedAlertRecord 唯一，无重复模型 |
| 列出迁移与不迁移文件 | ✅ | 见 §3.2 和 §3.3 |
| PR#22 仍有效的资产已提取 | ✅ | 4 个独有资产（CSV / 契约 md / 2 个 fixture / 4 条测试）全部升级迁入 |

### 9.2 第 2 步完成标准

| 标准 | 达成？ | 说明 |
|---|---|---|
| 运行 A 实际字段与四模型逐字段确认 | ✅ | 58 项逐字段核对，57 通过 1 待决策 |
| 字段契约包已形成 | ✅ | t0903-06-step2-contract-package.md 含顶层返回 + 必需字段 + 可选字段 + 原始留存 + traceBackId + 时间规则 + 四模型总览 |
| 字段性质标注（真实脱敏 vs 固定 fixture） | ✅ | official_desensitized_alert.json 标注为真实脱敏结构；fixed_alerts/ 标注为固定 fixture |

### 9.3 第 3 步完成标准

| 标准 | 达成？ | 说明 |
|---|---|---|
| 脱敏真实结构转换测试 | ✅ | 8 条覆盖基础映射/lastTime 优先/xdr_ 前缀/空数组过滤/null 过滤/traceBackId/url 保留/完整主链 |
| 固定样例回归 | ✅ | 2 条验证 FixedSampleAdapter 不被破坏 |
| 缺字段处理 | ✅ | 5 条覆盖 uuId/时间/name 缺失 + field_mapping 永不降级 + business code Fail 永不降级 |
| 空结果处理 | ✅ | 2 条覆盖 item=[] → empty_result + allow_fallback=True 也不降级 |
| 去重回归 | ✅ | 4 条覆盖跨页同 uuId/精确 lookup/关联压缩/类型不匹配拒绝 |
| 全量回归无回归 | ✅ | 175 passed, 0 failed, 1 skipped（原 150 + 新增 21 + PR#22 升级 4） |

---

## 10. 遗留问题与后续步骤

### 10.1 遗留问题

| # | 问题 | 严重度 | 说明 | 建议修复方向 |
|---|---|---|---|---|
| 1 | **severity 数字 vs 字符串专项升级未统一** | ⚠️ 中 | `_xdr_severity()` 中 WebShell蚁剑专项升级条件是 `alert_grade == "高危"` 字符串精确匹配；真实 `severity=70`（int）传入为 `"70"`，永远不等于 `"高危"` → 蚁剑 WebShell 真实路径永远是 high/80，固定样例演示走 critical/95 | 统一专项升级条件为 `alert_name 匹配 + (numeric_severity>=70 OR alert_grade=="高危")`，需钱诺成决策 severity=70 语义是否等价"高危" |
| 2 | **部署时区假设未写入文档** | ⚠️ 中 | `_time_to_text()` 用 `datetime.fromtimestamp()` 取墙钟，隐含 Python 服务器时区 = Asia/Shanghai | 在部署文档记录时区要求；或改为显式 `timezone(timedelta(hours=8))` |
| 3 | **NormalizedAlertRecord.model_validate() 首路径冗余** | ℹ️ 低 | 官方脱敏结构字段全为 camelCase，大概率走第二条 raw→normalizer 路径；第一条为兼容旧 JSONL 固定样例保留 | 低优先级，代码冗余不影响功能 |

### 10.2 后续步骤（等待用户指示）

| 步骤 | 内容 | 状态 |
|---|---|---|
| **第 4 步** | 给闫昱硕的研判字段/证据摘要 + 给杨景凡的调查实体/证据引用摘要 | ⏸ 等待用户指示 |
| **第 5 步** | 增量更新告警接入与关联三份模块文档 | ⏸ 等待用户指示 |

### 10.3 Git 状态

```
分支：chenmin/t0903-6-origin-main-clean
基线：e154343 (origin/main)

新增/升级文件（全部为新增，无现有代码修改）：
AM docs/modules/platform-tools/xdr_field_mapping.csv          (PR#22 升级)
AM docs/modules/platform-tools/xdr_input_contract.md           (PR#22 升级)
AM tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json  (PR#22 升级)
AM tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json (PR#22 升级)
AM tests/test_xdr_input_contract.py                            (PR#22 升级)
?? docs/platform-tools/t0903-06-step1-audit.md                 (T0903-06 新增)
?? docs/platform-tools/t0903-06-step2-contract-package.md      (T0903-06 新增)
?? docs/platform-tools/t0903-06-archive.md                     (T0903-06 新增, 本文件)
?? tests/fixtures/xdr_openapi/official_desensitized_alert.json (T0903-06 新增)
?? tests/fixtures/xdr_openapi/official_desensitized_response.json (T0903-06 新增)
?? tests/test_t0903_06_contract_regression.py                  (T0903-06 新增)
```

---

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-03 | 首次建立 | T0903-06 前三步执行结果与检查核查结果存档 |
