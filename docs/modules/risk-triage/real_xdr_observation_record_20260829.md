# 风险研判 · 真实 XDR 观测记录（2026-08-29）

> 负责人：闫昱硕　|　记录日期：2026-08-29　|　对应任务：T0828-07 统一候选研判与真实现观测
> 分支：`feature/Yisee6`（已合并当前 `main`，含 XDR OpenAPI 真实平台接入）
> 真实数据来源：陈敏交付的真实 XDR 列表响应（脱敏样例 `xdr_list_alerts_response_sanitized.json`）及字段映射
> `xdr_field_mapping.csv`。该响应为真实平台字段（`platform_derived`），非固定/合成样例。

## 一、结论

1. **真实 XDR 数据可接入主链。** 使用陈敏交付的真实 XDR 列表响应（外字段 `uuId / name / firstTime / hostIp /
   srcIp / severity / confidence / gpt_result_desc / ruleName / attackStage`），经 `XdrOpenApiAdapter` 字段映射后
   能完整走通「映射 → 标准化 → 告警关联 → 风险研判 → 调查 → 处置建议」，主链落在 `APPROVAL_REQUIRED`。
2. **本轮补齐了真实平台字段映射缺口。** 主链合入前的 `XdrOpenApiAdapter` 只识别 `event_id / alert_time /
   alert_name / src_ip / destination_ip` 等内部字段，遇到真实平台外字段（`uuId`、`firstTime`、`hostIp`、
   `srcIp`、`ruleName`、`attackStage`）会报 `field_mapping` 中止。本轮已按 `xdr_field_mapping.csv` 在适配器
   增加真实 XDR 外字段映射，并把平台自带的 `confidence`、`gpt_result_desc`、`attackStage` 保留进
   `scenario_fields`。
3. **真实事件与固定 WebShell 样例存在严重度/种子差异。** 真实事件 `severity=high`，而固定样例
   `FIX-XDR-WEBSHELL-001` 被标准化器刻意升级为 `critical/95`，导致两者风险分（80 vs 95）不一致；但
   `verdict / confidence / priority` 一致。
4. **`VERDICT_CONFIDENCE` 仍为占位。** 真实平台已返回 `confidence=95`，但当前规则仍输出固定档位
   `0.85`。**单条真实事件不等于完成统计校准**，`VERDICT_CONFIDENCE` 继续标注为占位。

## 二、真实告警原始字段（按校准模板）

| 项目 | 字段 | 值 |
| --- | --- | --- |
| 唯一标识 | `uuId` | `alert-20260828-0001` |
| 告警名称 | `name` | `WebShell 攻击行为 (AntSword)` |
| 首次/最后时间 | `firstTime` / `lastTime` | `1724810000` / `1724810900`（Unix，映射后 `2024-08-28 09:53:20+08:00`） |
| 影响资产 IP | `hostIp` | `198.51.100.10` |
| 来源 IP | `srcIp` | `203.0.113.5` |
| 原始风险等级 | `severity` | `high` |
| 平台置信度 | `confidence` | `95` |
| GPT 研判描述 | `gpt_result_desc` | 检测到明显的蚁剑 WebShell 连接特征，攻击者正在尝试执行系统命令。 |
| 规则名称 | `ruleName` | `WebShell_Detection_Rule` |
| 攻击阶段 | `attackStage` | `Lateral Movement` |

## 三、字段映射结果（`XdrOpenApiAdapter` 输出）

| 映射后标准字段 | 值 | 来源 |
| --- | --- | --- |
| `alert_id` | `alert-20260828-0001` | `uuId` |
| `name` | `WebShell 攻击行为 (AntSword)` | `name` |
| `alert_type` | `webshell` | `name` / `ruleName` 语义 |
| `raw_severity` | `high` | `severity` |
| `occurred_at` | `2024-08-28 09:53:20+08:00` | `firstTime`（Unix→+08:00） |
| `src_ip` | `203.0.113.5` | `srcIp` |
| `dst_ip` / `assets` | `198.51.100.10` | `hostIp` |
| `scenario_fields.confidence` | `95` | `confidence` |
| `scenario_fields.gpt_result_desc` | 见上 | `gpt_result_desc` |
| `scenario_fields.stage` | `Lateral Movement` | `attackStage` |

## 四、当前规则输出（真实事件）

| 输出 | 值 | 计算 |
| --- | --- | --- |
| 严重度分 | 40 | `SEVERITY_POINTS[high]` |
| 攻击类型分 | 30 | `ATTACK_TYPE_POINTS[webshell]` |
| 规则分 `rule_score` | 70 | `40 + 30` |
| 风险种子 `risk_score_seed` | 80 | 由 `high` 派生 |
| 风险分 `risk_score` | 80 | `min(100, max(70, 80))` |
| verdict | `malicious` | `risk_score >= 70` |
| confidence | `0.85` | `VERDICT_CONFIDENCE[malicious]`（占位） |
| priority | `high` | 随 verdict |
| should_investigate | `True` | 非 benign 一律调查 |
| 证据引用 | `alert-20260828-0001:alert_time / alert_name / alert_grade / alert_classification / source_ip / destination_ip / host_ip` | `evidence_refs` 并集 |
| 证据缺口 | 无 | — |
| 处置目标 | `198.51.100.10`（隔离/限制通信，待人工审批） | 调查建议 |

主链状态：`APPROVAL_REQUIRED`　|　`effective_source=xdr_openapi`　|　`alert_refs=['alert-20260828-0001']`

## 五、与固定样例的差异（校准依据）

| 项目 | 固定样例 `FIX-XDR-WEBSHELL-001` | 真实事件 `alert-20260828-0001` | 差异 |
| --- | --- | --- | --- |
| 严重度 | `critical` | `high` | 固定样例被标准化器刻意升级为 `critical`，真实平台为 `high` |
| 风险种子 | `95` | `80` | 固定样例手工 `95`；真实事件按 `high` 派生 `80` |
| 规则分 | `90` | `70` | 随严重度不同 |
| 风险分 | `95` | `80` | 真实事件更低 |
| verdict | `malicious` | `malicious` | 一致 |
| confidence | `0.85` | `0.85` | 一致（均为占位） |
| priority | `high` | `high` | 一致 |

### 需要校准的常量

- **`VERDICT_CONFIDENCE`（占位，本轮不变更）**：真实平台已给 `confidence=95`，但规则忽略平台置信度，仍输出
  固定档位。单条真实事件不能据此调整，需累积足够样本后再校准并同步 `design.md` / `test.md` /
  `rule_placeholder_inventory.md`。
- **`SEVERITY_POINTS` / `risk_score_seed` 派生规则（待观察）**：固定 WebShell 样例被升级为 `critical/95`，
  而真实 WebShell 为 `high/80`。需更多真实 WebShell 样本判断严重度分档与种子派生是否符合真实分布。

## 六、与校准模板衔接

- 本记录 `期望*` 列对应 `calibration_record_template.csv` 的基线，用于后续真实数据逐条对比。
- CSV 记录见 `real_xdr_calibration_record_20260829.csv`。
- 机器可读结果见 `real_xdr_triage_results_20260829.json`。
