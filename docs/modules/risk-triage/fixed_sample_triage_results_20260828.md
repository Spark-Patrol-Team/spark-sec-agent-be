# 风险研判 · 固定样例实测结果（2026-08-28）

> 负责人：闫昱硕　|　日期：2026-08-28　|　分支：`feature/Yisee6`（已合并最新 `main`）
> 说明：本表为**真实数据接入前**，用项目内 `tests/fixtures/fixed_alerts` 固定告警样例跑 `RiskTriageService` 的实测结果。
> `sample_nature` 为 `platform_derived`（结构基于平台数据整理）或 `synthetic_regression`（合成回归样例），**不代表 8/28 真实平台告警**。
> `confidence` 为 `VERDICT_CONFIDENCE` 固定档位（仍为占位，未校准）。

## 一、运行方式

```bash
PYTHONPATH=src python -m pytest -q                       # 全量回归
PYTHONPATH=src python -m sec_agent.scripts.run_flow     # 端到端主流程
```

本轮全量回归：`135 passed, 1 skipped`（跳过项为未配置 `LLM_API_KEY` 的深度调查 LLM 可选用例）。

## 二、固定样例研判结果

| 样例 | 来源 | 严重度 | 攻击类型 | 种子分 | 关联前告警数 | 规则分 | 风险分 | verdict | confidence | priority | 是否调查 | 支持证据 | 缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FIX-XDR-WEBSHELL-001 | XDR(platform_derived) | critical | webshell | 95 | 1 | 90 | 95 | malicious | 0.85 | high | 是 | 7 | 无 |
| FIX-STA-SQLI-001 | STA(platform_derived) | high | sql_injection | 80 | 1 | 60 | 80 | malicious | 0.85 | high | 是 | 7 | 无 |
| FIX-STA-LATERAL-001 | STA(synthetic_regression) | medium | lateral_movement | 65 | 1 | 40 | 65 | uncertain | 0.65 | medium | 是 | 7 | 需要补充平台侧日志或上下文 |

## 三、逐条明细

### FIX-XDR-WEBSHELL-001

- `sample_nature`：platform_derived
- 原始字段：severity=`critical`，alert_type=`webshell`，seed=`95`，关联前告警数=`1`
- `rule_score`=90 → `risk_score`=95
- `verdict`=`malicious`，`confidence`=0.85，`priority`=`high`，`should_investigate`=True
- 支持证据：7 条（FIX-XDR-WEBSHELL-001:alert_time, FIX-XDR-WEBSHELL-001:alert_name, FIX-XDR-WEBSHELL-001:alert_grade, FIX-XDR-WEBSHELL-001:alert_classification, FIX-XDR-WEBSHELL-001:source_ip, FIX-XDR-WEBSHELL-001:destination_ip, FIX-XDR-WEBSHELL-001:host_ip）
- 缺口：无

- summary：规则基线判断为高风险，需要进入深度调查补充证据并生成处置建议

### FIX-STA-SQLI-001

- `sample_nature`：platform_derived
- 原始字段：severity=`high`，alert_type=`sql_injection`，seed=`80`，关联前告警数=`1`
- `rule_score`=60 → `risk_score`=80
- `verdict`=`malicious`，`confidence`=0.85，`priority`=`high`，`should_investigate`=True
- 支持证据：7 条（FIX-STA-SQLI-001:record_time, FIX-STA-SQLI-001:rule_name, FIX-STA-SQLI-001:reporting_device, FIX-STA-SQLI-001:source_ip, FIX-STA-SQLI-001:source_port, FIX-STA-SQLI-001:destination_ip, FIX-STA-SQLI-001:destination_port）
- 缺口：无

- summary：规则基线判断为高风险，需要进入深度调查补充证据并生成处置建议

### FIX-STA-LATERAL-001

- `sample_nature`：synthetic_regression
- 原始字段：severity=`medium`，alert_type=`lateral_movement`，seed=`65`，关联前告警数=`1`
- `rule_score`=40 → `risk_score`=65
- `verdict`=`uncertain`，`confidence`=0.65，`priority`=`medium`，`should_investigate`=True
- 支持证据：7 条（FIX-STA-LATERAL-001:record_time, FIX-STA-LATERAL-001:rule_name, FIX-STA-LATERAL-001:reporting_device, FIX-STA-LATERAL-001:source_ip, FIX-STA-LATERAL-001:source_port, FIX-STA-LATERAL-001:destination_ip, FIX-STA-LATERAL-001:destination_port）
- 缺口：需要补充平台侧日志或上下文

- summary：规则基线判断证据不足，需要进入深度调查

## 四、与校准模板的衔接

- 上表 `期望*` 列即 `calibration_record_template.csv` 的基线值，用于 8/28 真实数据进入后逐条对比。
- `VERDICT_CONFIDENCE`（malicious=0.85 / uncertain=0.65 / benign=0.70）**仍为占位**；单条真实事件不等于完成统计校准，需足够样本后再调整并同步 `design.md` / `test.md` / `rule_placeholder_inventory.md`。

