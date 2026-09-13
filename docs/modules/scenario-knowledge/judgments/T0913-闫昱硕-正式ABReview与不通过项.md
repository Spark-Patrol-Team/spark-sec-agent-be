# T0913 闫昱硕：10 案正式 A/B Review 与不通过项

> 负责人：闫昱硕　|　日期：2026-09-13　|　分支：`feature/t0913-yanyushuo-judgment-review-clean`（基于 `origin/main@9247624`）
> 依据：2026-09-13《3.7 闫昱硕判据与结果 Review》九项
> 判据：本目录 `case1.expected.json` ~ `case10.expected.json`（已绑定最终 case1-10 与 `WSK-*` 知识卡）

## 0. 证据链与边界（先说清楚哪些能直接复证）

| 证据 | 内容 | 本仓库可复证性 |
|---|---|---|
| 杨景凡 `T0905-07` 正式运行产物 | 10 份 `report_case*_guarded.json` + 10 份 `report_case*_off.json` + `e2e/_summary.json`（head `0eb38cc`） | ❌ 报告 JSON 是 `.gitignore` 运行产物，未入仓库；本轮未取得原始文件 |
| 肖迎春《T0905-05 正式 AB 结果处置边界复核》（2026-09-10） | 对上述同一批 20 份产物的 10 案逐案矩阵与 VERIFIED / NOT VERIFIED 分级 | ✅ 可读取；本文件第 2 节矩阵引自该复核 |
| 杨景凡《T0905-04 回执》 | 门禁绑定、`off/guarded` 注册差异、case6 两层验收 | ✅ 可读取 |

**结论口径**：本轮的 A/B 事实以「杨景凡产物的团队复核记录」为准，**不把未亲自读取的原始 JSON 写成自己实测**；凡引用复核记录处均已标注。若需逐字判定 case6 报告文本，须补 `report_case6_guarded.json` 原文。

## 1. 与 3.7 九项逐项对账

| # | 检查项 | 状态 | 证据 / 位置 |
|---|---|---|---|
| 1 | 从最新候选建立只包含判据、指标和 Review 材料的干净 PR | ✅ | 本分支基于 `origin/main@9247624`；仅新增 `docs/modules/scenario-knowledge/judgments/` 与 `tests/test_yanyushuo_expected_judgments.py` |
| 2 | 删除夹带的陈敏门禁、知识资产、case 输入和其他上游代码 | ✅ | 本分支相对 main 只新增判据/Review 与判据守护测试，不含 `gatekeeper.py`、`webshell-knowledge.md`、`caseN.json` 等上游产物 |
| 3 | 判据绑定最终 case1—10 和 `WSK-*` 知识 ID | ✅ | 10 份判据新增 `knowledge_ids_wsk`；`test_wsk_binding_matches_final_knowledge_cards` 校验 WSK ID 真实存在于唯一知识源且与 `K-WEBSHELL-*` 组展开一致 |
| 4 | 删除此前在没有 actual 包时形成的“正式 A/B 已完成”旧结论 | ✅ | `一致性review.md` 第 5.5 节旧结论已删除，改为指向本文件 |
| 5 | 使用杨景凡现有 A/B 结果包完成 10 案正式 Review | ✅（引用复核记录） | 第 2、3 节；原始 JSON 未入仓库这一点在第 0 节明示 |
| 6 | case6：`out_of_scope` 但报告出现 WordPress 供应链攻击倾向，判断是否越界 | ✅ | 第 4 节 |
| 7 | 解释 20 案全部 `need_manual_takeover=true` 的原因及可证明/不可证明内容 | ✅ | 第 5 节 |
| 8 | 完成来源—主张 Review、指标分母、置信度限制和 A/B 结论 | ✅ | 第 3、6 节 + `来源主张边界review.md` + `WSK来源主张边界review.md` + `指标口径与原始计数.md` |
| 9 | 对不通过项给出明确 case 编号、证据字段和最小修改要求 | ✅ | 第 7 节 |

## 2. 10 案正式运行矩阵

> 来源：肖迎春《T0905-05 正式 AB 结果处置边界复核》第 4 节（对杨景凡 `T0905-07` 正式 20 份产物的逐案复核）。

| case | gate_decision | guarded 知识 | off 知识 | 工具失败 | 报告结论 | 处置建议 | manual | T0905-05 scope / ResponsePlan |
|---|---|---|---|---|---|---|---|---|
| case1 | `weak_signal` | 2× `partial` | `not_registered` | 6 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case2 | `weak_signal` | 2× `partial` | `not_registered` | 3 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case3 | `weak_signal` | 2× `partial` | `not_registered` | 7 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case4 | `weak_signal` | 3× `partial` | `not_registered` | 3 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case5 | `weak_signal` | 1× `partial` | `not_registered` | `query_asset=failed` | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case6 | `out_of_scope` | 3× `failed(knowledge_scope_mismatch)` | `not_registered` | 3 failed | 供应链攻击长结论，无法闭环验证 | 含条件性取证/隔离建议 | true | `NOT_PRESENT` |
| case7 | `weak_signal` | 未调用 | `not_registered` | 4 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case8 | `weak_signal` | 2× `partial` | `not_registered` | 5 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case9 | `in_scope` | 3× `success`（命中 `WSK-010`/`WSK-001`/`WSK-015`，7 条引用） | `not_registered` | 3 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |
| case10 | `out_of_scope` | `failed(knowledge_scope_mismatch)` | `not_registered` | 9 failed | 证据不足 | 人工介入 | true | `NOT_PRESENT` |

## 3. A/B 结论（10 案）

**按判据口径逐项判定**

| 判定项 | 结论 | 依据 |
|---|---|---|
| `off` 组是否注册/调用知识 | ✅ 全部 `not_registered`，无一调用 | 矩阵 off 列 |
| `guarded` 是否按三档放行知识 | ✅ `in_scope` 成功、`weak_signal` 仅 `partial`、`out_of_scope` 被 `scope_mismatch` 拒绝 | 矩阵 guarded 列；case9 命中 `WSK-010/001/015` |
| 弱信号是否被知识升级成确认 | ✅ 未观察到：case1-5、7、8 报告结论均为“证据不足 + 人工接管”，无确认性知识 | 矩阵报告结论列 |
| 域外案是否被解释成 WebShell | ⚠️ 知识侧否（case6/10 均被拒绝）；**报告文本侧** case6 存在 WebShell 关联推断（见第 4 节） | 矩阵 case6 行 + T0905-05 §5.3 |
| 知识引用是否冒充原始证据 | ✅ 未观察到：case9 的 7 条引用位于 `evidence_source`，未进入 `key_evidence` | T0905-05 §6 |
| 工具失败是否被写成调查成功 | ✅ 未观察到：case5 真实 `query_asset=failed`，报告仍为证据不足 + 人工接管 | T0905-05 §5.4 |
| 处置链是否被知识升级 | ⚠️ **NOT VERIFIED**：20 份报告均无 `response_evidence_scope` / `ResponsePlan` / `disposition` | T0905-05 §7 / §8 |

**可以正式宣称**

- 本批 10 个指定案例中，`off` 与 `guarded` 的知识工具行为符合三档门禁口径；**未观察到**任何一档因开启知识而产生“确认攻击、植入、持久化、载荷、工具失败写成成功”的报告级升级。

**不能宣称**

- 不能宣称“处置链（resolver → ResponsePlan → disposition）已验证”：报告层不含 scope/plan/disposition。
- 不能宣称准确率、召回率、置信度校准或百分比收益；本批为 10 个 synthetic 案例。
- 不能宣称 case6 报告文本逐字合规：需 `report_case6_guarded.json` 原文才能逐字判定。

## 4. case6 越界判定（重点）

**事实（引自 T0905-05 第 4 节与 §5.3）**

- 输入：WordPress 插件/供应链异常，无任何 WebShell 证据；门禁 `out_of_scope`；`guarded` 知识查询 3 次全部 `failed(knowledge_scope_mismatch)`。
- 报告结论：`供应链攻击长结论，无法闭环验证`；处置建议：`含条件性取证/隔离建议`；并且“报告文本出现 WebShell 关联推断”。

**分层判定**

| 层 | 是否越界 | 说明 |
|---|---|---|
| 知识层（工具返回） | ❌ 不越界 | `out_of_scope` 下知识查询被 `knowledge_scope_mismatch` 拒绝，未返回任何 WebShell 卡；与本判据 `case6.expected.json` 的 `forbidden_knowledge_ids`（全部 WebShell 知识）一致 |
| 报告层（结论文本） | ⚠️ **存在越界风险** | `out_of_scope` 案的结论不应出现 WebShell 关联推断，也不应把事件定性为“供应链攻击”。判据 `case6.expected.json` 允许的结论只有“该事件为 WordPress 插件/供应链异常，非 WebShell 域”“当前 WebShell 知识不适用，记录知识缺口”。报告写成“供应链攻击长结论”已超出“记录异常与缺口”的范围，属于**定性越界**（不是知识越界） |
| 处置层（ResponsePlan） | 未越界（也未被验证） | 报告无 `ResponsePlan`/`disposition`，未形成可执行 WebShell 处置；该层为 `NOT VERIFIED` |

**判定结论**：case6 的问题**不是知识门禁失效**（门禁正确拒绝），而是**报告结论生成缺少“域外案不得定性/不得做 WebShell 关联推断”的代码级约束**。当前只能按 T0905-05 记录的“文本语义观察项”登记；升级为缺陷需 `report_case6_guarded.json` 原文逐字对照。

**最小修改要求（case6）**

- 证据字段：`report.conclusion`（guarded）、`report.disposal_suggestions`（guarded）。
- 要求 1：`out_of_scope` 案 `conclusion` 只允许“非本领域 + 记录知识缺口/转交其他链路”，禁止出现 WebShell 关联推断与攻击定性。
- 要求 2：`out_of_scope` 案 `disposal_suggestions` 不得出现“取证/隔离”这类可读作处置动作的建议，或必须显式标注“非 WebShell 域，仅为一般性建议”。
- 要求 3：补一条自动检查（复述输入 + 禁止关键词集），把该约束纳入回归。
- 归属：杨景凡（报告生成约束与自动检查）；陈敏门禁无需改动。

## 5. 20 案 `need_manual_takeover=true` 的解释

**事实**：杨景凡正式 20 份报告（10 案 × `off/guarded`）全部 `need_manual_takeover=true`，且均无可执行 WebShell cleanup/containment plan（T0905-05 §3 VERIFIED）。

**原因（三条叠加，非异常）**

1. **门禁只决定知识适用性，不决定是否自动处置**：三档 `gate_decision` 的作用是放行/限制/拒绝知识，本批 10 案的证据强度整体不足以自动执行 WebShell 处置（含 case9 `in_scope`，其结论仍是“证据不足 + 人工介入”）。
2. **高风险处置默认需审批**：处置执行侧默认只读（`ALLOW_REAL_HIGH_RISK_ACTION=false`），高风险动作必须走人工审批，故报告层一律置为需人工接管。
3. **域外/工具失败案按规则转人工或转其他链路**：case5（工具失败）、case6/case10（域外）均按规则转人工。

**能证明**

- 报告层行为保守且一致：没有任何一案因开启知识而生成可执行处置；`off` 与 `guarded` 在这一点上无差异。
- 知识增强没有把任何一档“变成自动处置”。

**不能证明**

- 不能证明处置链真实运行（报告无 `response_evidence_scope`/`ResponsePlan`/`disposition`）。
- 不能证明“人工接管”这个判断本身正确：这需要人工 Review 记录，本批未提供。
- **不能把 `need_manual_takeover=true` 当作“分级正确”的通过证据**：20/20 全为 true，说明该字段在当前实现里**没有区分度**（`in_scope` 与 `out_of_scope` 取值相同），无法用它区分“证据不足转人工”“高风险需审批”“域外转其他链路”三种不同语义。这是口径缺陷，登记为不通过项（第 7 节 #2）。

## 6. 来源—主张 Review / 指标分母 / 置信度限制

- **来源—主张 Review**：见 `来源主张边界review.md`（案例级）与 `WSK来源主张边界review.md`（15 张 WSK 卡）。本轮**未新增一手来源**，不改变既有等级判定；仍待补：WSK-013 官方根因、case3（Beima/Cyderes）原始来源（归属沈洪旭）。
- **指标分母**：见 `指标口径与原始计数.md`；本轮补 A/B 分母 `case × mode = 10 × 2 = 20`。
- **置信度限制**：`confidence` 为固定/构造值或规则种子分主导，且本批预测置信度未做统计校准；不得据本批宣称“置信度校准完成”。

## 7. 不通过项与最小修改要求

| # | case | 不通过项 | 证据字段 | 最小修改要求 | 归属 |
|---|---|---|---|---|---|
| 1 | case6 | 域外案报告结论出现 WebShell 关联推断与“供应链攻击”定性 | `report.conclusion`（guarded）、`report.disposal_suggestions`（guarded） | 见第 4 节要求 1-3：结论限定为非本领域 + 记录缺口；禁止 WebShell 关联推断与攻击定性；补自动检查 | 杨景凡（报告约束） |
| 2 | case6、case10（并影响全 20 报告） | 判据 `human_required=false`，正式报告 `need_manual_takeover=true`；且 20/20 全 true、字段无区分度 | `report.need_manual_takeover` | 明确“域外案人工接管”的语义（转其他链路 ≠ 无法判定），并在判据与报告中取同一口径；必要时补 `takeover_reason` 字段区分三类原因 | 闫昱硕（判据口径）+ 杨景凡（报告）+ 李雨妍（Schema，如需新字段） |
| 3 | 全部 10 案 | 报告缺 `response_evidence_scope` / `ResponsePlan` / `disposition`，处置链 NOT VERIFIED | `report`（顶层） | 报告顶层记录 scope 与 plan；若该层明确不属于 Agent 报告，须在契约中写清楚由谁产出、如何关联 | 肖迎春 + 李雨妍 + 杨景凡 |
| 4 | case10 | 判据 `expected_tool_status.knowledge_query=not_called`，实际为“调用后被 `scope_mismatch` 拒绝” | `report.tool_call_records` | 判据口径已在本轮明确为“`not_called` 或明确记录 `scope_mismatch` 均判通过”；无需改代码 | 闫昱硕（已收口） |
| 5 | case1-5、7、8 | `guarded` 知识为 `partial`、报告 0 条知识引用 | `report.tool_call_records`、`report.evidence_source` | 无需修改：符合判据“弱信号不得返回确认性知识” | — |
| 6 | case9 | 知识引用 7 条位于 `evidence_source` | `report.evidence_source` | 无需修改：符合“知识引用 ≠ 原始证据” | — |
| 7 | 全部 | 迁移前“正式 A/B 已完成”旧结论 | `一致性review.md` §5.5（原） | 已删除；正式结论以本文件为准 | 闫昱硕（已收口） |

## 8. 本轮交付边界

- ✅ 干净 PR：只含判据、指标与 Review 材料；不含上游门禁/知识资产/case 输入代码。
- ✅ 判据绑定最终 case1-10 与 `WSK-*`，并有守护测试（9 通过）。
- ✅ 删除旧“正式 A/B 已完成”结论，改用有实际运行产物复核支撑的正式 Review。
- ⚠️ 残留：case6 报告原文本轮未取得，越界判定为“文本语义观察项 + 最小修改要求”，未升级为已确认缺陷；处置链 NOT VERIFIED。
- ⚠️ 未改：case6/case10 判据 `human_required` 与报告 `need_manual_takeover` 的口径冲突（第 7 节 #2）——改判据需与杨景凡/李雨妍对齐后再定，本轮先登记不改。
