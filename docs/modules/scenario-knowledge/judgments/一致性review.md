# 与陈敏事件信号合同的一致性 Review（闫昱硕）

> 本文件是 T0905-03 交付物 #5/#6：把 10 份正式判据与陈敏 `PR#43` 的 case1-10 事件输入（`tests/fixtures/gatekeeper_cases/caseN.json`）做一致性核验，并登记固定置信度/平台种子分等已知限制与 A/B 研判影响结论（待杨景凡结果）。

## 1. 一致性基线

- 输入合同：陈敏 `PR#43` head `500f65c` 的 `tests/fixtures/gatekeeper_cases/case1.json ~ case10.json`。
- 门禁实现：`src/sec_agent/services/gatekeeper.py`（`WebShellGatekeeper`）。
- 期望强度断言：`tests/test_gatekeeper_case1_10.py::TestTask6HandoverAssertions::test_yanyushuo_signal_strength_and_verdict`。
- 判据：本目录 `case1.expected.json` ~ `case10.expected.json`。

## 2. 逐案一致性核验

| case | 输入是否含判据所需的强信号 | 判据是否引用知识补事实 | 弱信号是否误设 in_scope | 域外负向是否保持 | 人工接管是否与证据缺口相符 | 一致结论 |
|---|---|---|---|---|---|---|
| case1 | 弱信号（异常访问/octet-stream/Base64/AES） | 否，仅用知识作调查方向 | 是 weak_signal ✅ | 不适用 | 否（可继续自动调查） | ✅ 一致 |
| case2 | 输入含强信号（反序列化/内核驱动/进程隐藏） | 否，但需复述输入事实 | 是 in_scope ✅ | 不适用 | 是（高风险+需人工核实） | ⚠️ 判据与判据内部一致，但**case2 输入与来源 Review 冲突**（见来源 Review 3.1） |
| case3 | 含 RSA 强关键词，整体偏弱 | 否 | 弱信号，保守收口 ✅ | 不适用 | 是（政府目标+来源弱） | ⚠️ 门禁可能因 RSA 判 CONFIRMED，判据按来源边界收口 weak_signal（属判据修正，非输入错误） |
| case4 | 仅文件名弱信号 | 否 | weak_signal ✅ | 不适用 | 是（上下文缺失） | ✅ 一致 |
| case5 | 弱信号（工具失败） | 否 | weak_signal ✅ | 不适用 | 是（关键工具失败） | ✅ 一致 |
| case6 | 非 WebShell 域 | 否，禁止套用 | 否 | out_of_scope ✅ | 否 | ✅ 一致 |
| case7 | 弱+良性（合法上传） | 否 | weak_signal，保留良性可能 ✅ | 不适用 | 否 | ✅ 一致 |
| case8 | 仅文件名弱信号 | 否 | weak_signal ✅ | 不适用 | 否（低危，保留不确定） | ✅ 一致 |
| case9 | 强信号组合（异常POST→文件改→cmd→回显） | 否 | in_scope ✅ | 不适用 | 是（高风险处置需审批） | ✅ 一致 |
| case10 | 证据侧域外（SSH暴力） | 否 | 否 | out_of_scope ✅ | 否 | ⚠️ 判据与证据侧一致，但**`event_type` 误标为 WebShell**，属输入口径问题（需陈敏修正） |

## 3. 发现的问题清单（按“由谁修正”归属）

| # | 问题 | 归属修正 | 建议处置 |
|---|---|---|---|
| 1 | case2 输入（Godzilla/ViewState/Wingtb.sys/进程隐藏）与来源 Review 冲突，且与沈洪旭 case2（部署尝试未成功）互斥 | 陈敏（输入字段/信号） | **⏳ 仍未处理**：陈敏本次只改门禁代码，case 输入未变。确认 case2 回归“部署尝试未成功”，或补直接来源；来源补齐前判据按 conservative 口径，不作家族/持久化定论 |
| 2 | case10 输入 `event_type=WebShell`，与全部 SSH 暴力证据矛盾 | 陈敏（输入字段） | **⏳ 仍未处理**：case10 输入未变。更正为 `SSH`/`Brute_Force` 或 `other`；判据已按证据侧域外收口并记录该口径矛盾 |
| 3 | alerts/evidence 字段位置冲突 | 陈敏（门禁代码） | **✅ 已修复**：gatekeeper 已统一从 `alerts` 与 `evidence` 抽取信号；旧版 case1-6 已删除，现统一以 `tests/fixtures/gatekeeper_cases/case1-10.json` 为准 |
| 4 | 门禁 `_extract_triage_signal` 使 `initial_verdict` 的 verdict 信号未生效 | 陈敏（门禁代码） | **✅ 已修复**：verdict 信号现正常生成（`forbidden_triage_read` 仍作无害标记保留）；判据口径不变 |
| 5 | case3 门禁因 `RSA解密函数` 强关键词判 `IN_SCOPE_CONFIRMED` | 陈敏（门禁代码） | **✅ 已修复**：`RSA解密函数` 已降为弱信号，门禁判 `IN_SCOPE_WEAK`，与判据一致；来源边界仍限定 Beima 家族不得确认 |

> 处理规则：输入字段/信号错误由陈敏修正；证据强度/结论上限错误由闫昱硕（本判据）修正；知识卡内容越界由沈洪旭按 Review 意见修改；不复制另一套判据。

## 4. 已知限制（固定置信度 / 平台种子分）

当前系统可能仍存在：

- **固定置信度**：case 输入的 `confidence` 为构造值（如 case1=0.76、case4=0.35），并非模型估计；
- **规则种子分/平台原始风险分**：`risk_score_seed` 主导最终风险分（见 `t0903-06-step4-summary-for-yanyushuo-judgment.md`，`event_type` 从 `other`→`sql_injection` 变化 20 分，但 `risk_score=80` 仍由 `risk_score_seed` 主导）；
- **简化阈值**与**未校准的风险映射**（severity 数字路径与中文专项升级路径存在 15 分差异，XDR-MAP-020 遗留未决）；
- **部署时区假设**：服务器墙钟必须为 `Asia/Shanghai`，否则时间偏移 8 小时。

> **结论**：当前风险分主要由固定规则或平台种子分决定。本批 A/B 只能观察知识增强对**报告行为与证据边界**的影响，**不能**证明置信度已完成统计校准，也不能据此宣称知识增强提升了固定百分比。

本批**不扩展**为：重做评分模型、重新标注大规模数据、训练校准模型、建立完整精确率/召回率评测、调整全部风险阈值。

## 5. A/B 研判影响结论（待杨景凡结果，本批暂无法给出）

杨景凡尚未交付 `off/guarded` A/B 结果，本批**不能**给出“至少 6 案 A/B 的研判影响结论”。收到结果后按以下口径补登记，并只做**本批 10 案**内的观察：

| 案例 | off 风险/置信度 | guarded 风险/置信度 | 是否变化 | 变化是否有新证据支持 | 结论 |
|---|---|---|---|---|---|
| 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |

### 合理 vs 不合理变化（检查口径）

- **合理**：调查步骤更完整；发现应检查的证据缺口；正确提示误报可能；引用更合适知识卡；更清楚区分事实与通用知识；正确转人工。
- **不合理（判为风险）**：事件输入与工具结果完全相同，仅因开启知识就出现风险等级无依据升高、置信度大幅提高、从“可疑”变“已确认”、新增输入中不存在的植入/执行/持久化/最终载荷、负向案例被解释成 WebShell、工具失败被写成调查成功、生成更强处置建议。

> 若事件输入与工具结果相同、仅有知识增强导致显著分数提升，且无新事件/工具证据支撑，应登记为**限制或缺陷**，不视为知识增强有效。

## 6. 收口状态

- ✅ 三档证据强弱与结论上限规则：`证据强弱与结论上限规则.md`
- ✅ case1-10 十份正式判据：`case1.expected.json` ~ `case10.expected.json`
- ✅ 来源—主张边界 Review：`来源主张边界review.md`
- ✅ 指标分母与原始计数口径：`指标口径与原始计数.md`
- ✅ 一致性 Review：本文件
- ⏳ 至少 6 案 A/B 研判影响结论：**待杨景凡交付后补登记**
- ✅ 固定置信度/平台种子分等已知限制：本文件第 4 节
