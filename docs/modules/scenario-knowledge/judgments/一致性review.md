# 与陈敏事件信号合同的一致性 Review（闫昱硕）

> 本文件是 T0905-03 交付物 #5/#6：把 10 份正式判据与陈敏 `PR#43` 门禁、沈洪旭 `PR#44` 的 case1-10 事件输入（`docs/modules/scenario-knowledge/knowledge-test-cases/caseN.json`）做一致性核验，并登记固定置信度/平台种子分等已知限制与 A/B 研判影响结论。**第 5 节 A/B 当前为「预演」**（mock 门禁行为对照），正式结论待杨景凡 ≥6 案真实 A/B 结果后补最后一遍 Review。

## 1. 一致性基线

- 输入合同：陈敏 `PR#43` head `7baa412`（门禁三档判定）+ 沈洪旭 `PR#44` 的 `docs/modules/scenario-knowledge/knowledge-test-cases/case1.json ~ case10.json`（case1-6 扁平结构、case7-10 包裹结构）。
- 门禁实现：`src/sec_agent/services/gatekeeper.py`（`WebShellGatekeeper`，只输出 `overall_strength` 6 级 + `gate_decision` 三档，不再做 95/75 风险升级）。
- 期望强度断言：`tests/test_gatekeeper_case1_10.py::TestTask6HandoverAssertions::test_yanyushuo_signal_strength_and_gate`。
- 判据：本目录 `case1.expected.json` ~ `case10.expected.json`。

## 2. 逐案一致性核验

| case | 输入是否含判据所需的强信号 | 判据是否引用知识补事实 | 弱信号是否误设 in_scope | 域外负向是否保持 | 人工接管是否与证据缺口相符 | 一致结论 |
|---|---|---|---|---|---|---|
| case1 | 弱信号（异常访问/octet-stream/Base64/AES） | 否，仅用知识作调查方向 | 是 weak_signal ✅ | 不适用 | 否（可继续自动调查） | ✅ 一致 |
| case2 | 输入为 PassiveNeuron 部署尝试且被阻断（无成功证据） | 否 | weak_signal ✅ | 不适用 | 是（CRITICAL+部署尝试需人工核实） | ✅ 一致（已按来源 Review 收敛为弱信号） |
| case3 | 含 RSA 强关键词，整体偏弱 | 否 | 弱信号，保守收口 ✅ | 不适用 | 是（政府目标+来源弱） | ⚠️ 门禁可能因 RSA 判 CONFIRMED，判据按来源边界收口 weak_signal（属判据修正，非输入错误） |
| case4 | 仅文件名弱信号 | 否 | weak_signal ✅ | 不适用 | 是（上下文缺失） | ✅ 一致 |
| case5 | 弱信号（工具失败） | 否 | weak_signal ✅ | 不适用 | 是（关键工具失败） | ✅ 一致 |
| case6 | 非 WebShell 域 | 否，禁止套用 | 否 | out_of_scope ✅ | 否 | ✅ 一致 |
| case7 | 弱+良性（合法上传） | 否 | weak_signal，保留良性可能 ✅ | 不适用 | 否 | ✅ 一致 |
| case8 | 仅文件名弱信号 | 否 | weak_signal ✅ | 不适用 | 否（低危，保留不确定） | ✅ 一致 |
| case9 | 强信号组合（异常POST→文件改→cmd→回显） | 否 | in_scope ✅ | 不适用 | 是（高风险处置需审批） | ✅ 一致 |
| case10 | 证据侧域外（SSH暴力） | 否 | 否 | out_of_scope ✅ | 否 | ✅ 一致；`event_type=WebShell` 为故意保留的误标测试桩，门禁以 `input_quality_issues` 保守标注 |

## 3. 发现的问题清单（按“由谁修正”归属）

| # | 问题 | 归属修正 | 建议处置 |
|---|---|---|---|
| 1 | case2 输入（Godzilla/ViewState/Wingtb.sys/进程隐藏）与来源 Review 冲突，且与沈洪旭 case2（部署尝试未成功）互斥 | 陈敏（输入字段/信号） | **✅ 已解决**：PR#44 已将 case2 收敛为 PassiveNeuron 部署尝试被阻断（`初始verdict=疑似WebShell部署尝试`，无成功证据）；判据已按 `weak_signal` 收口 |
| 2 | case10 输入 `event_type=WebShell`，与全部 SSH 暴力证据矛盾 | 陈敏（门禁代码） | **✅ 已由门禁保守标注**：PR#43 门禁在 `input_quality_issues` 记录“event_type=WebShell 与 SSH 暴力破解冲突、确认为误标”，同时按证据判 `OUT_OF_SCOPE`；`event_type` 保留原样作为数据质量测试桩，不再改源头 |
| 3 | alerts/evidence 字段位置冲突 | 陈敏（门禁代码） | **✅ 已修复**：gatekeeper 已统一从 `alerts` 与 `evidence` 抽取信号；旧版 case1-6 已删除，现统一以 `docs/modules/scenario-knowledge/knowledge-test-cases/case1-10.json` 为准 |
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

## 5. A/B 研判影响结论（预演 Rehearsal：基于杨景凡回执 + 门禁实测登记，非正式结果）

> ⚠️ **本节约为「预演」（Rehearsal）**：数据来自**确定性 mock 知识门禁行为对照**（非真实 LLM 逐案 `off/guarded` 风险分/置信度），仅用于先验证判据口径与知识增强的证据边界，**不**代表正式 A/B 结论。
>
> **正式 Review 待办**：等杨景凡跑出**至少 6 案真实 `off/guarded` A/B 结果**后，基于**同一份正式结果**补最后一遍 Review，重点核验知识增强有没有让“风险判断、置信度或结论”在**证据不足**的情况下变强（沿用 5.4 检查口径，把“不合理变化”登记为风险/缺陷）。
>
> 数据来源：杨景凡《T0905-04 回执》顺序 3/4（8 代表性案 A/B 行为）+ 本批在工作分支用 `WebShellGatekeeper.audit` 对同一 8 案实测。两类数据一致。
>
> A/B 形式说明：本批 A/B 是**确定性（mock）知识门禁行为对照**——`off` 不注册知识工具、`guarded` 注册并按门禁档位放行/拒绝知识；它**不提供**逐案 `off/guarded` 的真实 LLM 风险分/置信度数值。故登记表以“门禁 6 档 / 三档 scope / 知识放行或拒绝”代替风险分数值列，据此给出研判。

### 5.1 8 案 A/B 对照（确定性 mock）

| 案例 | 场景（category） | 输入severity | 门禁6档 | 三档scope | guarded 知识 | off 知识 |
|---|---|---|---|---|---|---|
| case1 | 正向变体 | HIGH | IN_SCOPE_WEAK | weak_signal | 放行(WEAK) | not_registered |
| case9 | 正向变体 | CRITICAL | IN_SCOPE_CONFIRMED | in_scope | 放行(CONFIRMED) | not_registered |
| case8 | 弱信号/证据不足 | LOW | IN_SCOPE_WEAK | weak_signal | 放行(WEAK) | not_registered |
| case7 | 合法业务误报 | MEDIUM | MIXED | weak_signal | 放行(WEAK) | not_registered |
| case4 | 证据不足 | MEDIUM | IN_SCOPE_WEAK | weak_signal | 放行(WEAK) | not_registered |
| case5 | 证据不足 | HIGH | IN_SCOPE_WEAK | weak_signal | 放行(WEAK) | not_registered |
| case6 | 非WebShell对照 | HIGH | OUT_OF_SCOPE | out_of_scope | 拒绝(scope_mismatch) | not_registered |
| case10 | 域外事件 | MEDIUM | OUT_OF_SCOPE | out_of_scope | 拒绝(scope_mismatch) | not_registered |

> case2/3 不在杨景凡指定代表 8 案内（顺序 3 固定为 1/9/8/7/4/5/6/10），故本批 A/B 为 **8/10 案**，满足“≥6 案”。

### 5.2 研判结论

- **知识增强未制造证据、未越界**：门禁 6 档／三档均由事件证据与信号决定，**与是否开启知识无关**；guarded 只是通过 `fold_scope` 把门禁结果透传给知识工具，不改风险等级。
- **正向/弱/误报案放行知识、弱不升确认**：case9 CONFIRMED→放行完整知识；case1/8/4/5 WEAK→仅放行弱档知识（“仅供参考、不构成攻击确认”）；case7（MIXED→WEAK）→放行但保留“合法业务／缺行为证据”可能。均未出现“从可疑变已确认”。
- **负向/域外案正确关闭知识**：case6/10 OUT→返回稳定错误码 `knowledge_scope_mismatch`，不返回任何 WebShell 知识；顺序 4 第二层已验证 OUT 案报告降级为“证据不足＋人工接管”，不出现 WebShell 植入/通信/持久化/载荷/清除/攻击确认。
- **合理变化**：guarded 让正向/弱案“知道该查什么、该保留哪些证据缺口”，让负向案“知道当前知识不适用”，属证据边界内增强。

### 5.3 限制与登记为风险/缺陷的点

| # | 现象 | 判读 | 归属处理 |
|---|---|---|---|
| 1 | 本批 A/B 为**确定性 mock 行为对照**，无逐案 `off/guarded` 真实 LLM 风险分/置信度数值 | **限制**：只能观察“知识工具行为与证据边界”，**不能**宣称知识增强提升风险分/置信度或完成统计校准 | 杨景凡（需真实 LLM + `--event` 全流程复跑，见其“遗留点 2”） |
| 2 | `fold_scope` 对空/未知 strength **默认返回 CONFIRMED（fail-open 放行知识）** | **缺陷/风险**：无证据时知识被放行，属放行过宽；建议改 fail-closed（未知默认 WEAK 或 OUT） | 杨景凡（“遗留点 3”） |
| 3 | case7（合法业务误报）`MIXED → WEAK`，与正向弱信号同档、都放行攻击知识，未单设“良性”档 | **口径风险**：误报档与弱信号档语义未区分，可能让“合法业务”也被当弱信号触发攻击知识 | 陈敏/杨嘉琪（“遗留点 1”）；本判据 case7 已按“允许 MIXED/BENIGN_LIKE/WEAK 且保留良性可能”收口，需与三档口径对齐 |

> 若事件输入与工具结果相同、仅有知识增强导致显著分数提升，且无新事件/工具证据支撑，应登记为**限制或缺陷**，不视为知识增强有效——本批为 mock 行为对照，未观察到此类显著分数提升。

### 5.4 合理 vs 不合理变化（检查口径，后续真实 LLM A/B 沿用）

- **合理**：调查步骤更完整；发现应检查的证据缺口；正确提示误报可能；引用更合适知识卡；更清楚区分事实与通用知识；正确转人工。
- **不合理（判为风险）**：事件输入与工具结果完全相同，仅因开启知识就出现风险等级无依据升高、置信度大幅提高、从“可疑”变“已确认”、新增输入中不存在的植入/执行/持久化/最终载荷、负向案例被解释成 WebShell、工具失败被写成调查成功、生成更强处置建议。

## 6. 收口状态

- ✅ 三档证据强弱与结论上限规则：`证据强弱与结论上限规则.md`
- ✅ case1-10 十份正式判据：`case1.expected.json` ~ `case10.expected.json`
- ✅ 来源—主张边界 Review：`来源主张边界review.md`
- ✅ 指标分母与原始计数口径：`指标口径与原始计数.md`
- ✅ 一致性 Review：本文件
- ✅ 至少 6 案 A/B 研判影响结论（**预演**）：已登记（见第 5 节；8/10 案，含限制与缺陷点）
- ⏳ 正式 A/B 最终 Review：待杨景凡 ≥6 案真实 A/B 结果后，基于同一份正式结果补最后一遍，重点核验知识增强是否让风险判断/置信度/结论在证据不足时变强（见 5.4 检查口径）。
- ✅ 固定置信度/平台种子分等已知限制：本文件第 4 节
