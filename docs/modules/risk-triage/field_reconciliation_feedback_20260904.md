# 风险研判 · 字段核对反馈（2026-09-04）

> 接收人：陈敏（字段确认人）
> 发起人：闫昱硕（研判复验）
> 依据：陈敏《T0903-06 下游摘要（一）：研判字段/证据摘要》（契约版本 `2026-09-03.t0903-chenmin-v1`）
> 核对对象：真实事件 `evt-9b6df22d-bbb5-4d84-b340-a969099bcfc9`（2026-09-02 运行，`effective_source=xdr_openapi`）

## 一、核对结论

稳定字段 10 项中，7 项与真实事件一致；3 项需要陈敏确认或统一口径。研判最终结论（`malicious / 0.85 / 80 / high / 应调查`）在字段口径变化下仍稳定，因 `risk_score=80` 由平台种子分主导，规则分构成会随 `event_type` 变化（见下）。

| # | 字段 | 9/2 真实事件 | 与契约一致性 |
| --- | --- | --- | --- |
| 1 | `event_type` | `other` | ⚠️ 需确认（旧路径按 name 关键词判 other） |
| 2 | `severity` / `risk_score_seed` | `high` / `80` | ✅ 一致（`severity=70 → high/80`） |
| 3 | `occurred_at` | `2026-08-21T13:43:23+08:00` | ✅ 一致（带 +08:00） |
| 4 | `assets` | `192.168.100.200` | ✅ 一致 |
| 5 | `source_device_name` | `STA (STA_001-04AABE1B)` | ⚠️ 见下（非 "XDR" 回退常量） |
| 6 | `src_ip` | `192.168.100.100` | ✅ 一致 |
| 7 | `dst_ip` | `192.168.100.200` | ✅ 一致 |
| 8 | `evidence_refs` | 33 项 | ⚠️ 命名口径需统一 |
| 10 | 枚举转换 | `severity` ✅；`event_type` ⚠️ | 见下 |

## 二、需陈敏确认 / 统一的三点

### 1. `event_type` 旧路径判 `other`，请用新 6 层链回放

真实告警 `uuId=alert-9fd0c034-ba09-4311-8360-cf1787206450`、`name="SQL server数据库查询sa账户密码攻击"`。9/2 旧代码按名称关键词（要求 `sql` 且含“注入”）判成 `other`。

请确认该真实告警的 `threatSubTypeDesc / riskTag / threatTypeDesc / threatClassDesc` 是否有值：

- 若有且为「SQL注入」，则新链（`9c6f00d`）应映射为 `sql_injection`；
- 若这些官方分类字段为空，则落到第 6 层 `name`，而「sa 账户密码攻击」不在「SQL注入」关键词内，仍可能判 `other`。

如属后者，建议在 name 回退层补充「sa 账户密码攻击 / SQL 查询」这类模式，否则真实 SQL 注入会持续被低估（研判攻击类型分=0）。

### 2. 证据字段命名口径漂移

9/2 观察到的证据引用里是原始名 `gptResultDescription / attackState / confidence / alertDealAction`；9/3 契约统一为 `xdr_*` 前缀（`xdr_gptResultDescription / xdr_attackState / xdr_confidence`），且 `attackState`（0/2）与旧样例的 `attackStage`（数值 30）字段名不一致。

请确认最终字段名，我据此同步更新研判观察记录，避免文档口径漂移。

### 3. 来源设备非 "XDR" 回退常量

真实事件 `source_device_name = "STA (STA_001-04AABE1B)"`，说明该告警是 XDR 前置机聚合的 STA 来源，而非回退常量 `"XDR"`。这符合契约回退链，但提示真实 XDR 列表可能混入 STA 来源告警，研判文档需说明来源设备可能非 XDR。

## 三、对研判的影响（记录，不阻塞）

- `event_type` 由 `other`（攻击分 0）变为 `sql_injection`（攻击分 20）后，规则分由 `40` 变为 `60`，但最终 `risk_score=80` 仍由 `risk_score_seed=80` 主导，`verdict / confidence / priority` 不变。研判结论稳定，仅「规则贡献 vs 种子贡献」的构成不同。
- 「WebShell 蚁剑 severity 统一口径未决策」不影响本事件（本事件为 SQL，`severity=70 → high/80`），仅作为已知遗留项记录。

## 四、陈敏复核结论（2026-09-04，已对齐）

陈敏已按《T0903-06 下游摘要（一）研判字段/证据摘要》修订确认，三点反馈的处置如下：

| 反馈项 | 处置 | 是否需研判侧继续改 |
| --- | --- | --- |
| `event_type=other` | 新 6 层链 + `name` 回退（`sa账户密码` / `SQL 查询`）→ `sql_injection`；官方分类为「异常操作」时也能兜底 | 无需改研判代码；研判观察记录按新口径说明 |
| 证据字段命名 | **非 bug**，两层命名约定：`evidence_refs[].ref_id` 用 XDR API 原始名（无 `xdr_` 前缀）；`scenario_fields` 用 `xdr_*` 前缀；`attackState`(0/2) ≠ `stage`/`xdr_stage`(阶段数值) | 文档澄清即可 |
| `source_device_name` 非 `"XDR"` | 符合契约：`devSourceName[]` 优先链，真实列表可混入 STA 来源告警；仅三字段全空才回退 `"XDR"` | 文档澄清即可（勿视 `"XDR"` 为唯一合法值） |

**研判结论稳定性**：`event_type` 从 `other`（0）变为 `sql_injection`（20）后，规则分 40→60，但 `risk_score=80` 仍由 `risk_score_seed=80` 主导，`verdict / confidence / priority` 不变。

> 备注：`ATTACK_TYPE_POINTS` 中 `sql_injection=20`，故规则分为 `40(high) + 20 = 60`，非 30/70。
