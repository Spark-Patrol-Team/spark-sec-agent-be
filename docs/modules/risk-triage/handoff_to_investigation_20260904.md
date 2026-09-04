# 研判 → 深度调查 交接包（2026-09-04）

> 形成人：闫昱硕　|　日期：2026-09-04　|　依据：李雨妍 Review 通过的研判干净分支（PR #38）
> 目的：让杨景凡**无需翻阅 PR** 即可判断调查输入与调查触发；同时供钱诺成作为合并决定依据。
> 说明：本包针对真实事件 `evt-9b6df22d-bbb5-4d84-b340-a969099bcfc9`；**IP/设备序列号已脱敏**，杨景凡从事件本身取准确实体值。

## 一、统一候选

| 项 | 值 |
| --- | --- |
| 分支 / PR | `feature/t0829-risk-triage-clean` → `main`（PR #38，`mergeable_state=clean`） |
| 候选 Commit | `80bf711`（研判干净分支 HEAD） |
| 字段契约 | `2026-09-03.t0903-chenmin-v1`（陈敏），`event_type` 经 name 回退可判 `sql_injection` |
| 测试基线 | `pytest tests/test_triage.py -q` → 20 passed；全量 `pytest -q -rs` → 162 passed, 1 skipped（跳过=未配 `LLM_API_KEY` 深调可选用例） |

## 二、运行标识与来源

| 项 | 值 |
| --- | --- |
| `event_id` | `evt-9b6df22d-bbb5-4d84-b340-a969099bcfc9` |
| `run_id` | `run-776923de-7218-48aa-8c7a-a9fee2694a1f` |
| `trace_id` | `trace-c9a22655-e6af-47c4-83e5-9402842a559b` |
| `alert_id` | `alert-9fd0c034-ba09-4311-8360-cf1787206450` |
| 来源 | `effective_source=xdr_openapi`、`fallback_source=null`（未回退 fixed_sample） |
| 主链状态 | `APPROVAL_REQUIRED`（调查已产生，处置等待审批） |

## 三、研判输出（调查触发依据）

| 输出 | 值 | 说明 |
| --- | --- | --- |
| `verdict` | `malicious` | 确认识别为 `sql_injection`（name 回退），攻击分 20 |
| `confidence` | `0.85` | `VERDICT_CONFIDENCE` 占位，非证据校准置信度 |
| `risk_score` | `80` | 由平台 `risk_score_seed=80` 主导；规则分 60 = `high(40)+sql(20)` |
| `priority` | `high` | 随 verdict |
| `should_investigate` | `True` | 非 benign 一律触发 |
| `supporting_evidence_refs` | 33 项 | 7 基础字段 + `traceBackId` + `gptResultDescription/attackState/confidence/alertDealAction` + 21 条 `network_security_log-*` |
| `opposing_evidence_refs` | `[]` | 无 |
| `evidence_gaps` | `[]` | 无（资产/src/dst/evidence 空值属契约正常，非异常） |

## 四、调查输入实体（杨景凡按此取事件实际值）

| 角色 | 字段 | 脱敏示例 | 说明 |
| --- | --- | --- | --- |
| 源 | `src_ip` | `198.51.100.10` | 取自 `srcIp[]` 首 |
| 目的/资产 | `dst_ip` / `assets` | `198.51.100.20` | 取自 `dstIp[]` 首 / 回退 `hostIp` |
| 来源设备 | `scenario_fields.source_device_name` | `STA_001-****` | `devSourceName[]` 优先链，可非 `"XDR"` |
| 事件类型 | `event_type` | `sql_injection` | 已确认 |
| 严重级别 | `severity` | `high` | `severity=70 → high/80` |

可用的原始线索字段（存于 `scenario_fields.xdr_*`）：`xdr_gptResultDescription`（"真实攻击成功"）、`xdr_attackState`（0/2）、`xdr_confidence`、`xdr_riskTag`、`xdr_stage`（阶段数值，≠ `xdr_attackState`）；`traceBackId` 含 21 条 `network_security_log-*`。

## 五、交接使用方式

- 若杨景凡的「运行 B」（真实 MCP 调查）已完成：本包仅用于**统一验收与文档一致性**，不要求重跑。
- 若未完成：以运行 B 配置执行——`PLATFORM_BACKEND=xdr_openapi`、`XDR_ALLOW_FIXED_SAMPLE_FALLBACK=false`、`INVESTIGATION_BACKEND=deep_agent`、`DEEP_AGENT_TOOL_MODE=mcp`；查询参数必须来自本包第二节运行标识与第四节实体，**不得使用虚构样例**。
- 提醒：`risk_score=80` 由平台种子分主导，研判结论不完全由规则驱动；`confidence=0.85` 为占位，调查时不要把它当作已校准置信度。

## 六、审定记录

- 风险研判干净 PR：#38（李雨妍 Review 通过）
- 本交接包同时交钱诺成作为合并决定依据。
