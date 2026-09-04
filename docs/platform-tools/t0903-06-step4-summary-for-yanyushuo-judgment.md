# T0903-06 下游摘要（一）：给闫昱硕的研判字段/证据摘要

> 接收人：闫昱硕（最终研判复验）
> 撰写人：陈敏（字段确认人）
> 基线 Commit：`main@e154343`（含 PR#33 `e3cca8f`）+ 本任务提交 `9c6f00d`
> 稳定字段契约版本：`2026-09-03.t0903-chenmin-v1` + `xdr_field_mapping.csv` XDR-MAP-001 ~ MAP-020
> 契约文件：`docs/modules/platform-tools/xdr_field_mapping.csv`、`docs/platform-tools/t0903-06-step2-contract-package.md`

---

## 一、稳定字段清单（可直接用于研判打分，无需二次查询平台）

| # | 研判维度 | 代码字段来源（稳定 Commit） | 字段名 | 类型/枚举 | 是否**可能为空** | 备注 |
|---|---|---|---|---|---|---|
| 1 | **事件类型**（必填） | `NormalizedAlertRecord.event_type` ← `threatSubTypeDesc → riskTag → threatTypeDesc → alert_classification → threatClassDesc → name` | `event_type` | 枚举：`sql_injection` / `webshell` / `lateral_movement` / `unauthorized_access` / `other` | ❌ 永不空（未知值强制落 `other`） | **稳定**：6 层优先链；官方字段含「SQL注入」时直接映射（如脱敏 fixture `alert-9fd0c034…`）。⚠️ **9/2 旧路径**仅按 name 关键词（须同时含 `sql`+「注入」）会判 `other`；**9/3 新链**已补 name 回退（`sa账户密码` / `SQL 查询`），覆盖官方分类为「异常操作」但 name 为「SQL server…sa账户密码攻击」的真实告警。 |
| 2 | **XDR 严重级别**（必填） | `NormalizedAlertRecord.severity` ← `severity:int` 数字优先 → 中文回退 → 蚁剑专项升级 | `severity` | 枚举：`critical` / `high` / `medium` / `low` + 对应的 `risk_score_seed: 0~100` | ❌ 永不空（未知值强制落 `medium/65`） | **稳定，但有 1 个需决策的遗留**：真实 `severity=70`（int）对应 `high/80`，固定样例中 WebShell蚁剑走了 `critical/95` 中文专项升级。数字路径与字符串专项升级条件未统一（见 XDR-MAP-020），影响研判分差约 15 分。 |
| 3 | **时间**（必填） | `AlertRecord.occurred_at` ← `lastTime → firstTime → updateTime`（int Unix 秒戳 + 补 `Asia/Shanghai`） | `occurred_at` | `datetime(tz-aware, +08:00)` | ❌ 永不空（三字段同时缺失才 ValueError） | **稳定**：时间三字段官方必回，优先级 lastTime→firstTime→updateTime 是字段包中已确认规则；⚠️ 隐含部署假设：服务器时区 = Asia/Shanghai（不同时区环境 occurred_at 会偏移）。 |
| 4 | **资产**（条件必填） | `AlertRecord.assets` ← `affected_asset` = `destination_ip`（dstIp[] 首）→ 回退 `hostIp` | `assets: list[str]` | ✅ **可能为空**：当 dstIp=[] 且 hostIp 也缺失时，assets=[] | **稳定**：destination→host 回退链已在 CSV MAP-008 + 关联模块第 7 条设计决策确认。资产为空时应在人工研判中补填。 |
| 5 | **来源设备**（必填） | `AlertRecord.scenario_fields.source_device_name` ← `devSourceName[] → engineName[] → devUidDesc[] → 常量 "XDR"` | `source_device_name` | string | ❌ 永不空（全部缺失回退 "XDR"） | **稳定**：真实 XDR 列表常返回前置机/探针名（如 `STA (STA_001-04AABE1B)`），**不等于**回退常量 `"XDR"`；仅三字段全空时才落 `"XDR"`。研判时勿将 `"XDR"` 视为唯一合法值。 |
| 6 | **源实体**（可选） | `AlertRecord.src_ip` + `SecurityEvent.entities.src_ips` ← `srcIp[]` 首（官方数组） | `src_ip: str \| None` | ✅ **可能为空**：srcIp[] 全空数组或 null → None | **稳定**：数组取首 + 空数组回退 None。固定样例 src IP 100% 非空；真实 XDR 黄佳丽/闫昱硕观察值中 srcIp 均有值，但契约保留空语义。 |
| 7 | **目的实体**（可选） | `AlertRecord.dst_ip` + `SecurityEvent.entities.dst_ips` ← `dstIp[]` 首 → 回退 `hostIp` | `dst_ip: str \| None` | ✅ **可能为空**：dstIp 和 hostIp 同时缺失 → None | **稳定**：同资产规则。 |
| 8 | **证据引用**（必填） | `TriageResult.supporting_evidence_refs` ← `AlertRecord.evidence_refs` + `SecurityEvent.alert_refs` + `NormalizedAlertRecord.evidence_refs` | `evidence_refs: list[EvidenceRef|str]` | ✅ **可能为空**：traceBackId 空数组且无标准化字段引用时，evidence_refs 为空 | **稳定但可能为空**：证据引用由两部分组成：①字段引用 `ref_id={alert_id}:{官方原始字段名}`（如 `…:gptResultDescription`、`…:attackState`，**不带** `xdr_` 前缀，`kind=xdr_field`）② traceBackId（`kind=xdr_traceback`）。原始值留存于 `scenario_fields.xdr_*`（如 `xdr_gptResultDescription`、`xdr_attackState`）。⚠️ `attackState`（0/2）≠ `stage`/`xdr_stage`（阶段数值，如 30）。traceBackId 为空时跳过，**不伪造证据**。 |
| 9 | **哪些字段可能为空**（人工研判补填清单） | — | — | — | — | 汇总 4 项空语义：`assets=[]`（dstIp+hostIp 双空）、`src_ip=None`（srcIp 空数组）、`dst_ip=None`、`evidence_refs=[]`（traceBackId 全空）。**这 4 项空值符合契约，不代表接入异常**。 |
| 10 | **哪些值经过枚举转换**（与原始值的映射表） | `severity` + `event_type` + `attack_status` | — | 字典映射 | — | （1）`severity:int` → 分级枚举 + risk_seed：≥90→critical/90，≥70→high/80，≥50→medium/65，<50→low/30；中文：严重→critical、高危→high、中危→medium、低危→low。（2）官方威胁分类（`threatSubTypeDesc` 等）→ 事件类型枚举：`SQL注入→sql_injection`，`WebShell→webshell`，其余→继续下一层；name 回退：`sql`+「注入」或 `sa账户密码`/`SQL 查询` → `sql_injection`。（3）`status="new"` 固定值。 |

---

## 二、当前对应代码 Commit

- **字段映射链 Commit**：`9c6f00d`（本任务最新提交） → `src/sec_agent/platforms/xdr_openapi.py`（`_to_normalizer_raw()` + `_with_raw_context()`）+ `src/sec_agent/platforms/raw_jsonl.py`（`_normalize_xdr()` + `_xdr_severity()` + `_xdr_event_type()`）
- **关联与研判衔接 Commit**：`main@e154343`（PR#33 merge 点） → `src/sec_agent/services/correlation.py`（15 分钟关联窗） + `src/sec_agent/services/triage.py`
- **测试验证 Commit**：`9c6f00d` → 175 passed, 1 skipped，含 58 项逐字段核对与 25 条端到端契约回归

---

## 三、研判注意事项（给闫昱硕）

1. ⚠️ **WebShell蚁剑 severity 统一口径未决策**：真实 XDR `severity=70` + `name="WebShell蚁剑工具文件管理"` → 代码返回 `high/80`；固定样例演示路径返回 `critical/95`。两条路径分差 15。**真实环境研判时，若蚁剑告警应走 critical 级别，需在风险策略中额外覆盖（而非依赖适配器的 severity 字段）**。
2. 🔒 **部署时区假设**：服务器墙钟必须是 Asia/Shanghai。Linux/CI 环境下 Ubuntu 默认 UTC 时若不设 TZ，时间会偏移 8 小时。建议研判打分时直接用 `occurred_at`（已带 +08:00），不要从 `scenario_fields.xdr_lastTime`（原始 int 戳）反推。
3. 🔍 **原始字段留存 vs 证据引用命名（口径已统一）**：
   - **`scenario_fields`**：30 个官方字段带 `xdr_` 前缀（如 `xdr_gptResultDescription`、`xdr_attackState`、`xdr_confidence`、`xdr_alertDealAction`），过滤 None/""/[]/{}。
   - **`evidence_refs[].ref_id`**：使用 XDR API **原始字段名**（无 `xdr_` 前缀），如 `{alert_id}:gptResultDescription`、`{alert_id}:attackState`。
   - **勿混淆**：`xdr_attackState`（攻击状态 0/2）与 `xdr_stage`（阶段数值，如 30）是不同字段；旧观察记录中的 `attackStage` 应更正为 `stage`/`xdr_stage`。
4. 📋 **空值不是错误**：4 项可能为空的字段（assets/src_ip/dst_ip/evidence_refs）空值均符合契约；当 evidence_refs 为空时需人工从原始响应补充或从 `xdr_gptResultDescription` 提取线索。

---

## 四、闫昱硕复验反馈核对（2026-09-04）

依据 `field_reconciliation_feedback_20260904.md`，对真实事件 `evt-9b6df22d…`（`alert-9fd0c034…`，2026-09-02 运行）核对结论如下：

| 反馈项 | 9/2 观察 | 当前口径 / 处置 |
|---|---|---|
| `event_type=other` | 旧路径仅 name 关键词（须 `sql`+「注入」） | 新 6 层链：官方含「SQL注入」→ `sql_injection`；官方为「异常操作」→ name 回退（`sa账户密码`/`SQL 查询`）→ `sql_injection` |
| 证据字段命名漂移 | 观察为 `gptResultDescription/attackState` | **设计如此**：`evidence_refs` 用原始名；`scenario_fields` 用 `xdr_*` 前缀（见第三节第 3 条） |
| `source_device_name=STA (…)` | 非 `"XDR"` 回退常量 | **符合契约**：devSourceName 优先，真实列表可混入 STA 来源告警（见字段 #5） |

**研判结论稳定性**：`event_type` 从 `other`（攻击分 0）变为 `sql_injection`（攻击分 20）后，规则分 40→60，但 `risk_score=80` 仍由 `risk_score_seed=80` 主导，`verdict/confidence/priority` 不变。
