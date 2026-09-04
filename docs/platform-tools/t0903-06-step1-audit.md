# T0903-06 陈敏：真实输入契约资产迁移 · 第 1 步审计

> 执行日期：2026-09-03
> 基线：`origin/main` @ `e154343`（已含 PR#33 完整版本 `e3cca8f`）
> 分支：`chenmin/t0903-6-origin-main-clean`

## 1. 九个判断点逐项结论

### 1.1 字段映射表是否仍有效？
**有效，但分散在两处，未集中成文档**。
- 核心映射在 `XdrOpenApiAdapter._to_normalizer_raw()`（[xdr_openapi.py:335-410](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L335)），覆盖 20+ 字段的 camelCase / snake_case / 数组取首多路回退，已对齐官方脱敏结构。
- XDR 专项归一化在 `RawJsonlNormalizer._normalize_xdr()`（[raw_jsonl.py:124-161](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/raw_jsonl.py#L124)），severity 数字/中文双路径、event_type 威胁分类字段链、destination_ip→host_ip 回退。
- 原始字段留存 `_with_raw_context()`（[xdr_openapi.py:451-509](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L451)），30 个真实字段带 `xdr_` 前缀进入 scenario_fields。
- **结论**：有效，应迁移/固化为契约包。

### 1.2 XDR 输入契约是否与当前实现一致？
**一致**。官方契约：
- Method：POST
- Path：`/api/xdr/v1/alerts/list`（config 默认值，[config.py:38](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/core/config.py#L38)）
- Body：`{"page":int, "pageSize":int, "startTimestamp":int?}`（[xdr_openapi.py:321-325](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L321)）
- Auth：官方签名 `XdrOfficialSigner`（[xdr_openapi.py:777-940](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L777)），支持 token / aksk / auth_code 三种模式

### 1.3 脱敏请求/响应样例是否还能用于测试？
**能用，但需要固化**。main 上脱敏样例散落：
- `tests/fixtures/fixed_alerts/`（固定回归样例，非真实 XDR）
- `tests/test_xdr_openapi_platform.py` 内联的 FakeResponse payload
- docs 里没有独立的脱敏真实结构 fixture

**建议**：把 `XDR_OpenAPI更新版(1).md` 第五部分的脱敏 JSON 结构固化为独立 fixture（如 `tests/fixtures/xdr_openapi/official_desensitized_response.json`），供后续契约测试直接引用。

### 1.4 分页规则是否有正式依据？
**有正式依据**。来自官方文档第 10 节：`page + pageSize + total + item`。
- `_alert_list_body()` 构造分页请求（[xdr_openapi.py:321-325](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L321)）
- `_extract_items()` 优先识别 `data.item`（[xdr_openapi.py:283-284](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L283)）
- `_extract_total()` + `_should_fetch_next_page()` 翻页（[xdr_openapi.py:298-319](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L298)）
- 防御上限 `alert_max_pages=20`（config 默认）

### 1.5 去重规则是否符合当前代码？
**符合**。
- fetch 阶段：`seen_ids: set[str]` 基于 `uuId`（优先）或整条 JSON 序列化兜底（[xdr_openapi.py:172-192](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L172)）
- correlation 阶段：`AlertCorrelationService.correlate()` 再次按类型/资产/设备/窗口四条件压缩（[correlation.py:23-71](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/services/correlation.py#L23)）
- **唯一键**：`uuId`（官方字段清单 11 节），代码里 `_alert_lookup_key()` 查找链首位（[xdr_openapi.py:719-720](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L719)）

### 1.6 缺字段和非法字段处理是否还需要保留？
**需要保留**，且 main 上已正确实现。
- 必需字段三缺一直接 `raise ValueError`（[xdr_openapi.py:349-350](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L349)），不降级
- ValidationError / RawAlertNormalizationError → `kind="field_mapping"` 的 `PlatformIngestError`，`allow_fallback=False`（[xdr_openapi.py:216-223](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L216)）
- 非法 HTTP 状态 / 业务 code → 正确的 ErrorKind 分发（[xdr_openapi.py:225-276](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L225)）

### 1.7 空结果语义是否正确？
**正确**。
- `empty.item[]` → `fetch_alerts()` 返回空列表 → 后续触发 `empty_result` 平台错误（[xdr_openapi.py:151-161](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L151)）
- 空数组/空字符串/null 均不入 scenario_fields（[xdr_openapi.py:486](file:///d:/竞赛/挑战杯专项赛/XH-202614_AI+安全大模型平台的智能体研究/spark-sec-agent-be/src/sec_agent/platforms/xdr_openapi.py#L486) 的 `value not in (None, "", [], {})`）
- 但 `attackState=0` 这种合法 enum 值会被保留（值不在过滤集合里）

### 1.8 契约测试是否能迁移？
**main 上已有 4 个专门的 XDR 契约测试**，且全量 150 passed：
- `test_xdr_openapi_platform.py`（20 个测试，含 auth_code / 官方签名 / POST body 分页 / 业务码校验 / 官方威胁分类字段 / lastTime 优先等）
- `test_raw_jsonl_ingest_and_correlation.py`（6 个，固定样例 + JSONL + correlation）
- `test_mvp_tool.py`（1 个，xdr_log_query）

**可直接继承，无需迁移**。

### 1.9 哪些内容已被当前 main 实现、不需要重复加入？
**main 已完整实现**，PR#22 风格的草稿不再需要：
- ✅ POST `/api/xdr/v1/alerts/list` 契约（路径已在 config 默认值）
- ✅ 官方签名 `XdrOfficialSigner`（auth_code / aksk / token 三种）
- ✅ `data.item` 单数字段分页
- ✅ `uuId` 唯一标识 + 本地精确过滤
- ✅ 真实字段 → 数组取首 / snake_case 回退链
- ✅ lastTime / firstTime / updateTime 三时间优先级
- ✅ threatSubTypeDesc → riskTag → threatTypeDesc → name 的 event_type 推导链
- ✅ severity 数字 50/70 + 中文 "严重/高危/中危/低危" 双路径
- ✅ 30 个原始字段带 `xdr_` 前缀留存
- ✅ traceBackId → EvidenceRef(xdr_traceback)
- ✅ `PlatformIngestError` 错误语义（auth/platform_error/field_mapping/empty_result/timeout/unreachable 六种 kind + retryable + allow_fallback）
- ✅ `NormalizedAlertRecord` 标准化模型
- ✅ `AlertRecord` 主链告警模型
- ✅ `AlertCorrelationService` 三告警关联压缩
- ✅ 150 passed 测试基线

**无需迁移的旧草稿**：PR#26 之前的任何 `GET /api/v1/alerts` 风格实现、不带 `item` 单数字段的老分页、不带 `uuId` 的旧唯一标识字段（`event_id` 优先）、不带 `threatSubTypeDesc` 的 event_type 推导、不带官方签名的旧 HMAC-SHA256 实现。

---

## 2. 迁移清单 / 不迁移清单

| 类型 | 文件 | 动作 | 原因 |
|---|---|---|---|
| ✅ 已被 main 完整实现，**无需迁移** | `src/sec_agent/platforms/xdr_openapi.py` | 保留 | POST /api/xdr/v1/alerts/list + XdrOfficialSigner + item 分页 + uuId + 数组取首 + lastTime 优先 + threatSubTypeDesc 链 + 30 字段留存 |
| ✅ 已被 main 完整实现，**无需迁移** | `src/sec_agent/platforms/raw_jsonl.py` | 保留 | `_normalize_xdr()` + `_xdr_severity()` 数字/中文双路径 + `_xdr_event_type()` 官方威胁分类链 |
| ✅ 已被 main 完整实现，**无需迁移** | `src/sec_agent/core/config.py` | 保留 | `xdr_alerts_path=/api/xdr/v1/alerts/list` + `xdr_alert_page_size/max_pages/start_timestamp/verify_ssl/alert_auth_type=auth_code` |
| ✅ 已被 main 完整实现，**无需迁移** | `src/sec_agent/domain/models.py` | 保留 | `AlertRecord` + `NormalizedAlertRecord` + `EvidenceRef` + `PlatformIngestError` |
| ✅ 已被 main 完整实现，**无需迁移** | `tests/test_xdr_openapi_platform.py` | 保留 | 20 个契约测试，覆盖 auth_code / 官方签名 / POST body 分页 / item 单数字段 / business code / threatSubTypeDesc / lastTime |
| ✅ 已被 main 完整实现，**无需迁移** | `tests/fixtures/fixed_alerts/` | 保留 | 固定样例回归基线 |
| 🔄 **PR#22 独有，已升级并迁入** | `docs/modules/platform-tools/xdr_field_mapping.csv` | **升级后迁入** | PR#22 原始 14 条 snake_case 占位符映射 → 20 条 official camelCase 映射（001-014 升级字段名 + 015-020 新增 PR#33 契约条目：raw_field_preservation / pagination / signature / deduplication / error_classification / severity_numeric_vs_string 遗留） |
| 🔄 **PR#22 独有，已升级并迁入** | `tests/test_xdr_input_contract.py` | **升级后迁入** | PR#22 原始 4 条早期占位符检查 → 4 条官方字段契约检查（request: POST / real endpoint / JSON body；response: item[] + camelCase + severity:int + Unix ts；adapter_expectations 对齐官方名；脱敏约束保留）；**4/4 通过** |
| 🔄 **PR#22 独有，已升级并迁入** | `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | **升级后迁入** | PR#22 占位符 `method=PROVIDER_DEFINED` + `pagination=PROVIDER_DEFINED_PAGE_OR_CURSOR` → 官方 `method=POST` + `endpoint=/api/xdr/v1/alerts/list` + `body={page,pageSize,startTimestamp?}` |
| 🔄 **PR#22 独有，已升级并迁入** | `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | **升级后迁入** | PR#22 占位符 `records[]` + snake_case（event_id/alert_time/alert_grade）→ 官方 `item[]` + camelCase（uuId/name/severity:int/lastTime:int/ firstTime:int/updateTime:int/srcIp[]/dstIp[]/traceBackId[]/threatSubTypeDesc/devSourceName[] 等）+ adapter_expectations 对齐官方字段名 |
| 🆕 需要新增（固化契约） | `tests/fixtures/xdr_openapi/official_desensitized_response.json` | **新增** | 从 `XDR_OpenAPI更新版(1).md` 第五部分脱敏 JSON 结构固化为独立 fixture，供契约测试引用 |
| ❌ **不迁移** | 任何 `GET /api/v1/alerts` 风格实现 | 丢弃 | 与官方 POST 契约冲突 |
| ❌ **不迁移** | 任何不带 `uuId` 的旧唯一标识链（如 `event_id` 优先、`alert_id` 优先） | 丢弃 | `uuId` 是官方确认的唯一标识字段 |
| ❌ **不迁移** | 任何不带 `item` 单数字段的老分页（如 `items` 优先） | 丢弃 | 官方分页结构明确为 `item` 单数字段 |
| ❌ **不迁移** | PR#22 §6 的 cursor 分页占位符 `page_token` | 丢弃 | 官方使用页码式分页，不是游标分页 |
| ❌ **不迁移** | PR#22 早期 severity 纯中文映射（无数字路径） | 丢弃 | 真实 severity 是 int（50/70/...），数字路径优先 |

---

## 3. 本步完成标准自评

| 标准 | 达成？ |
|---|---|
| 不带回旧候选路径 | ✅ POST /api/xdr/v1/alerts/list 是唯一接口契约，无 GET 旧实现残留 |
| 不带回旧鉴权结论 | ✅ 官方签名唯一，无自带 HMAC 旁路 |
| 不带回第二套上层告警对象 | ✅ AlertRecord / NormalizedAlertRecord 唯一，无重复模型 |
| 列出迁移与不迁移文件 | ✅ 见上方表格 |
