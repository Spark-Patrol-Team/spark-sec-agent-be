# 风险研判 · 真实 XDR 观测记录（2026-09-02）

> 负责人：闫昱硕　|　记录日期：2026-09-02　|　对应任务：T0828-07 统一候选研判与真实现观测（另一条真实事件）
> 统一后端：`http://124.221.234.124`　|　输入来源：`xdr_openapi`
> 真实链路：真实 XDR 告警经统一服务器进入统一主链，`effective_source=xdr_openapi`、`fallback_source=null`（未发生 `fixed_sample` 回退）。
> 说明：本记录仅为**一条真实事件的一次研判观察与固定样例差异记录**，不构成统计校准、准确率验证或全场景阈值优化。

## 一、运行标识

| 字段 | 值 |
| --- | --- |
| `event_id` | `evt-9b6df22d-bbb5-4d84-b340-a969099bcfc9` |
| `run_id` | `run-776923de-7218-48aa-8c7a-a9fee2694a1f` |
| `trace_id` | `trace-c9a22655-e6af-47c4-83e5-9402842a559b` |
| `status` | `APPROVAL_REQUIRED` |
| `source / requested_source` | `xdr` / `xdr` |
| `effective_source` | `xdr_openapi` |
| `fallback_source` | `null` |
| `schema_version` | `2026-08-21.mvp.v1` |
| `alert_refs` | `['alert-9fd0c034-ba09-4311-8360-cf1787206450']` |

## 二、结论（观察）

1. **真实 XDR 告警正确进入主链并完成研判**，状态 `APPROVAL_REQUIRED`，链路：`RECEIVED → CORRELATING → TRIAGED → INVESTIGATING → DECISION_READY → APPROVAL_REQUIRED`。
2. **本次关键观察——verdict 由平台种子分驱动，而非研判规则**：真实告警 `alert_type=other`（未识别类型），规则攻击类型分 = `0`；`risk_score=80` 来自 `risk_score_seed=80`（由 `severity=high` 派生），而规则分仅 `40`（`SEVERITY_POINTS[high]=40` + `other=0`）。若去掉种子分，`40` 会落到 `uncertain/medium(0.65)`，因此 `verdict=malicious` 是被上游平台 `risk_score_seed` 抬上去的，**不是风险研判规则本身的攻击类型识别贡献**。
3. **与固定 WebShell 样例差异**：`FIX-XDR-WEBSHELL-001` 被标准化器刻意升级为 `critical/95`（规则分 `90=60+30`）；本真实事件 `high/80`（规则分 `40`）。两者风险分不同（`80 vs 95`），但 `verdict / confidence / priority` 一致。
4. **与 8/29 真实 WebShell 事件差异**：两条真实事件最终 `risk_score` 都是 `80`，但构成不同——8/29 为 `webshell`（规则分 `70=40+30`），本次为 `other`（规则分 `40=40+0`）。说明当 `risk_score_seed` 偏高时，规则攻击类型表对最终风险分的贡献会被种子分掩盖。
5. **`VERDICT_CONFIDENCE` 仍为占位**：真实平台已回传 `confidence`（进 `scenario_fields`），但规则仍输出固定档位 `0.85`。单条真实事件不足以据此调整，继续标注为占位。

## 三、脱敏输入字段摘要

| 项目 | 字段 | 值（已脱敏） |
| --- | --- | --- |
| 唯一标识 | `alert_id`（`uuId`） | `alert-9fd0c034-…-cf1787206450` |
| 事件类型 | `alert_type` | `other` |
| 严重级别 | `raw_severity` | `high` |
| 风险种子 | `risk_score_seed` | `80`（由 `high` 派生） |
| 来源设备 | `source_device` | `STA (STA_001-****)`（XDR 前置机聚合的 STA 来源告警） |
| 源地址 / 目的地址 / 影响资产 | `entities` | `198.51.100.10` / `198.51.100.20` / `198.51.100.20`（脱敏自内网地址） |
| 时间 | `first_seen_at` = `last_seen_at` | `2026-08-21T13:43:23+08:00` |
| 关联规模 | `alert_count_before` / `event_count_after` | `1` / `1` |
| 关联依据 | `correlation_reason` | `同一事件类型 other；目标资产 198.51.100.20；来源设备 STA (STA_001-****)；时间窗口 2026-08-21T13:43:23+08:00 至 2026-08-21T13:43:23+08:00，不超过 15 分钟` |
| 证据引用 | `supporting_evidence_refs` | 共 `33` 项：7 个基础字段 + `traceBackId` ×1 + 其它 XDR 字段 ×4（`gptResultDescription`、`attackState`、`confidence`、`alertDealAction`）+ `traceBackId:network_security_log-*` ×21 |

## 四、当前规则输出（真实事件）

| 输出 | 值 | 计算 |
| --- | --- | --- |
| 严重度分 | `40` | `SEVERITY_POINTS[high]` |
| 攻击类型分 | `0` | `ATTACK_TYPE_POINTS[other]` 未命中 |
| 规则分 `rule_score` | `40` | `40 + 0` |
| 风险种子 `risk_score_seed` | `80` | 由 `high` 派生 |
| 风险分 `risk_score` | `80` | `min(100, max(40, 80))` |
| verdict | `malicious` | `risk_score >= 70` |
| confidence | `0.85` | `VERDICT_CONFIDENCE[malicious]`（占位） |
| priority | `high` | 随 verdict |
| should_investigate | `True` | 非 benign 一律进入调查 |
| supporting_evidence_refs | `33` 项 | 证据引用并集 |
| opposing_evidence_refs | `[]` | 无反对证据模型 |
| evidence_gaps | `[]` | 无缺口（即使攻击类型为 `other` 也未标记缺口） |
| summary | 高风险，进入深度调查补充证据并生成处置建议 | — |

## 五、与固定样例 / 8/29 真实事件差异（校准依据）

| 项目 | 固定 `FIX-XDR-WEBSHELL-001` | 8/29 真实 WebShell | 本次真实 `other` | 差异说明 |
| --- | --- | --- | --- | --- |
| 攻击类型 | `webshell` | `webshell` | `other` | 本次类型未识别，攻击类型分归零 |
| 严重度 | `critical` | `high` | `high` | 固定样例被刻意升级 |
| 规则分 | `90`（60+30） | `70`（40+30） | `40`（40+0） | 攻击类型贡献不同 |
| 风险种子 | `95` | `80` | `80` | 固定样例手工 95 |
| 风险分 | `95` | `80` | `80` | 本次与 8/29 同为 80，但构成不同 |
| verdict | `malicious` | `malicious` | `malicious` | 一致 |
| confidence | `0.85` | `0.85` | `0.85` | 均为占位 |
| priority | `high` | `high` | `high` | 一致 |
| 证据引用 | 7 个基础字段 | 7 个基础字段 | 33 项（含日志引用） | 真实链路证据更丰富 |
| evidence_gaps | `0` | `0` | `0` | — |

### 需要校准的常量 / 待观察点

- **`VERDICT_CONFIDENCE`（占位，本轮不变更）**：真实平台已给 `confidence`，但规则仍输出固定档位；需累积足够真实样本后再校准。
- **未知攻击类型的语义缺口**：`alert_type=other` 时攻击分计 0，但当前规则**不将其标记为证据缺口 / 待补充**，直接沿用平台种子分定级。建议在后续真实样本中观察「`other` 类告警」占比，评估是否需要在研判中增加「类型未知需人工确认」的缺口标记。
- **`SEVERITY_POINTS` / 种子派生规则（待观察）**：真实事件严重度与种子派生是否匹配真实分布，需更多真实样本判断。

## 六、测试命令与结果

```bash
PYTHONPATH=src python -m pytest tests/test_triage.py -q   # 20 passed
PYTHONPATH=src python -m pytest -q                        # 153 passed, 1 skipped
```

`1 skipped` 为未配置 `LLM_API_KEY` 的深度调查 LLM 可选用例，非研判回归。研判相关用例全部通过。

## 七、验收边界

- 可通过：**完成一条真实事件（`evt-9b6df22d-…`）的第一次研判观察与固定样例差异记录。**
- 禁止：将单条真实事件表述为**已完成统计校准、准确率验证或全场景阈值优化**。
