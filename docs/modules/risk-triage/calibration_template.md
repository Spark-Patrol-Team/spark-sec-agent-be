# 风险研判 · 真实数据校准表模板（8/28 使用）

> 负责人：闫昱硕　|　日期：2026-08-27　|　配套：`calibration_record_template.csv`、`rule_placeholder_inventory.md`
> 用途：8/28 真实 STA / XDR 数据进入后，逐条记录「原始字段观测 → 标准化字段 → 当前规则期望输出 → 真实 / 人工结论 → 差异 → 是否触发校准」，用于替换第一版固定值 / 经验阈值。
> **核心目标**：优先校准 `VERDICT_CONFIDENCE`（malicious=0.85 / uncertain=0.65 / benign=0.70），再协同校准严重度分、攻击类型分、关联加成与两条阈值。

---

## 一、需要观察的原始字段（按来源类型）

> 字段名以 `src/sec_agent/platforms/raw_jsonl.py` 与 `tests/fixtures/fixed_alerts/raw_to_normalized_mapping.csv` 为基线。请同时记录样本的 `sample_nature`（`platform_derived` / `synthetic_regression`），真实数据一律取 `platform_derived`。

### 1.1 STA 网络安全日志

| 原始字段 | 是否必填 | 用途 | 缺失处理 |
|---|---|---|---|
| `sample_id` | 是 | 唯一关联键 | 拒绝进入主链 |
| `record_time` | 是 | 事件时间（补 `+08:00`） | 拒绝进入主链 |
| `reporting_device` | 是 | 来源设备类型 | `unknown` 并标记数据不足 |
| `reporting_device_name` | 否 | 来源设备名 | 回退 `reporting_device` |
| `rule_name` | 是 | 规则名 / 事件分类 | 用「未命名规则」并标记数据不足 |
| `source_ip` / `source_port` | 源是 / 源端否 | 源地址 / 端口 | 缺失源地址标记数据不足，端口置空 |
| `destination_ip` / `destination_port` | 目的是 / 端否 | 目的地址 / 端口 | 目的地址缺失标记数据不足；端口置空 |
| `log_type` | 是 | 证据来源 | `xdr_unknown_log` |
| `sample_source` | 否 | 证据来源 / 样例来源校验 | 沿用 `log_type` 映射 |
| `threat_level_3` | 否 | 攻击定位（如横向移动） | 可空 |
| `raw_note` | 否 | 脱敏说明 | 可空 |

### 1.2 XDR 安全告警

| 原始字段 | 是否必填 | 用途 | 缺失处理 |
|---|---|---|---|
| `sample_id` | 是 | 唯一关联键 | 拒绝进入主链 |
| `alert_time` | 是 | 告警时间（补 `+08:00`） | 拒绝进入主链 |
| `alert_name` | 是 | 告警名称 / 事件分类 | 用「未命名告警」并标记数据不足 |
| `alert_grade` | 是 | 严重度映射（严重/高危/中危/低危） | 默认 `medium` |
| `alert_classification` | 是 | 事件类型（WebShell / 未授权 / 其他） | 映射 `other` |
| `source_ip` / `source_port` | 源是 / 端否 | 源地址 / 端口 | 缺失源地址标记数据不足 |
| `destination_ip` / `host_ip` | 目的是 / 退否 | 目的地址（`destination_ip` 缺失回退 `host_ip`） | 两者均缺则为空并标记 |
| `data_source` | 是 | 来源设备类型 | `XDR` |
| `source_device_name` | 否 | 来源设备名 | 回退 `data_source` |
| `sample_source` | 否 | 证据来源 / 样例来源校验 | `xdr_security_alert` |
| `raw_note` | 否 | 脱敏说明 | 可空 |

### 1.3 标准化后（研判实际消费）

| 标准字段 | 来源 | 说明 |
|---|---|---|
| `event_type` → `alert_type` | `alert_name` / `alert_classification` / `rule_name` | webshell / sql_injection / lateral_movement / unauthorized_access / other |
| `severity` → `raw_severity` | `alert_grade` / `rule_name` | critical / high / medium / low |
| `risk_score_seed` | 平台种子（`_risk_seed` 或专项规则） | 0~100 整数，非 int 或越界则忽略 |
| `affected_asset` | 优先 `destination_ip`，回退 `host_ip` | 受影响资产 |
| `evidence_refs` | 原始证据字段集合 | 写入 `supporting_evidence_refs` |
| `status` / `investigation_hint` / `recommended_action` | 状态 / 线索 / 建议 | 供后续调查与处置 |

---

## 二、期望输出（`TriageResult` 字段）

| 输出字段 | 类型 | 说明 |
|---|---|---|
| `verdict` | `malicious / uncertain / benign` | 由 `risk_score` 阈值映射 |
| `confidence` | `0~1` | 当前按 `VERDICT_CONFIDENCE[verdict]` 固定档位 |
| `risk_score` | `0~100` 整数 | `min(100, max(rule_score, seed))` |
| `priority` | `high / medium / low` | 与 verdict 对应 |
| `should_investigate` | `bool` | 非 `benign` 一律 `True` |
| `supporting_evidence_refs` | `list[str]` | 告警 `evidence_refs.ref_id` 并集 |
| `opposing_evidence_refs` | `list[str]` | 当前恒为空 |
| `evidence_gaps` | `list[str]` | 无证据 / uncertain 时补充 |
| `summary` | `str` | 结论摘要 |

---

## 三、逐条校准记录表（模板）

| 记录ID | 日期 | 来源类型 | 原始样例ID | 实际严重度 | 实际攻击类型 | 种子分 | 关联前告警数 | 规则分 | 期望verdict | 期望priority | 期望should_investigate | 期望confidence | 真实/人工结论 | 期望vs真实差异 | 需校准常量 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

> 说明：
> - **期望verdict/priority/confidence** 由当前规则（`triage.py`）计算得出，用于对比。
> - **真实/人工结论**：以平台告警真实性判定或人工复核结论为准，作为校准的 Y 值。
> - **差异**：若「真实结论」与「期望结论」不一致，或 confidence 与真实置信不符，则该样例触发校准。
> - **需校准常量**：填写需要调整的常量名（如 `VERDICT_CONFIDENCE`、`HIGH_RISK_THRESHOLD`、`SEVERITY_POINTS`…）。若无需调整则填「无」。

---

## 四、CSV 模板

可直接用 `calibration_record_template.csv` 批量记录。列头与第三节一致；表内已给出 3 条**基于固定样例**的示例行（仅演示格式，`sample_nature` 为 `platform_derived / synthetic_regression`，非 8/28 真实数据），正式记录请删除或替换为真实样例。

---

## 五、校准流程与验收

1. 8/28 接入真实数据后，按来源类型提取上述原始字段，逐条写入 CSV / 表格。
2. 用当前规则（`RiskTriageService.triage()`）计算每条「期望输出」，填 `期望*` 列。
3. 记录「真实 / 人工结论」作为 Y 值；凡 `verdict` 或 `confidence` 与真实不符，即标记差异与需校准常量。
4. 汇总冲突样例（每类攻击、每档严重度至少 N 条），据此调整 B 类常量；**优先 `VERDICT_CONFIDENCE`**。
5. 调整后运行：`PYTHONPATH=src python -m pytest tests/test_triage.py tests/test_state_flow.py -v`，确认边界测试不回归。
6. 将校准结论回写 `design.md`、`test.md` 与 `rule_placeholder_inventory.md`，并把 `VERDICT_CONFIDENCE` 从「占位」改为「已校准」。
