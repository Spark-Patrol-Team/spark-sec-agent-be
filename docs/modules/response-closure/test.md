# 处置闭环模块测试说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | response-closure |
| 本轮任务 | T0913：最终响应闭环完善、语义验收与交付准备 |
| 文档职责 | 测试范围、命令、实际结果、验收证据和已知测试边界 |
| 测试能力性质 | 本地单元/集成/主链测试；处置执行为 Stateful Mock |

## 1. 测试目标与证据等级

本轮测试验证 T0913 的六项基线：

1. scope 只有一个生产者和一个业务消费者；
2. scope 能沿真实主链从调查结果传递到 ResponsePlan；
3. 三份模块文档与当前实现口径一致；
4. 请求、受理、记录、设备生效和独立验证不混为一个成功状态；
5. A/B 材料覆盖强证据、弱证据、域外事件和工具失败四类调查行为；
6. Mock 执行链经过独立验证安全门槛。

证据等级严格区分：

- A/B 结果：只证明 Investigation/knowledge boundary 行为；
- 代码测试：证明 scope 传递、决策、执行、验证和最终状态门槛；
- Mock：证明本地流程与记录语义；
- 真实平台/设备：当前没有测试证据，不作生产能力结论。

## 2. 测试范围

| 范围 | 当前结论 |
|---|---|
| scope production/consumption | 已覆盖 |
| 调查工具结果进入领域 InvestigationStep.tool_result | 已覆盖 |
| structured event_type / evidence_summaries 优先 | 已覆盖 |
| weak signal、out-of-scope、knowledge gap | 已覆盖 |
| 执行失败和验证失败/未知 | 已覆盖 |
| Mock record 不等于 DEVICE_EFFECT | 已覆盖 |
| DEVICE_EFFECT + 独立成功验证进入 COMPLETED | 已覆盖 |
| 真实平台 accepted、recorded、device effect | 未覆盖，当前能力不存在 |

## 3. 目标场景与已有测试

### 3.1 Scope 与调查边界

位置：tests/test_response_boundaries.py。

已覆盖测试包括：

- test_scope_resolver_strong_evidence_is_in_scope
- test_scope_resolver_knowledge_refs_cannot_replace_weak_original_evidence
- test_scope_resolver_domain_external_event_is_out_of_scope
- test_scope_resolver_does_not_reclassify_domain_from_report_prose
- test_scope_resolver_single_cmd_process_is_only_weak_signal
- test_scope_resolver_single_w3wp_process_is_only_weak_signal
- test_scope_resolver_conflicting_structured_signals_fail_closed
- test_scope_resolver_uses_structured_evidence_summary_for_domain_boundary
- test_scope_resolver_tool_failure_is_weak_signal
- test_scope_resolver_missing_tool_result_is_weak_signal
- test_decision_fails_closed_when_scope_is_missing
- test_weak_evidence_does_not_generate_unconditional_high_risk_plan
- test_out_of_scope_contract_does_not_generate_webshell_response_plan
- test_knowledge_gap_does_not_generate_unconditional_high_risk_plan

### 3.2 主链传递与工具记录

位置：tests/test_deep_agent_bridge.py、tests/test_state_flow.py。

已覆盖：

- test_deep_agent_backend_maps_failed_tool_record_to_domain_step
- test_deep_agent_backend_maps_external_report_to_domain_report
- test_auto_backend_records_fallback_and_runs_internal_tool_chain
- test_fixed_sample_stops_at_approval_required
- test_approval_executes_and_requires_human_for_mock_effect
- test_rejected_approval_goes_human_required
- test_duplicate_approval_is_idempotent
- test_state_machine_rejects_illegal_transition

这些测试证明工具记录能够进入领域调查步骤，主链能够调用 resolver，并将 scope 传递到决策和方案，而不是只在模型层声明字段。

### 3.3 执行、验证和完成门槛

位置：tests/test_response_boundaries.py、tests/test_state_flow.py、tests/test_api_http.py。

已覆盖：

- test_tool_failure_does_not_become_effective_verification
- test_stateful_mock_success_does_not_prove_device_effect
- test_platform_request_success_does_not_prove_device_effect
- test_platform_record_success_does_not_prove_device_effect
- test_device_effect_is_the_only_layer_that_can_complete_verification
- test_failed_verification_tool_cannot_complete_from_device_effect_output
- test_approval_executes_and_requires_human_for_mock_effect
- test_event_http_flow_requires_human_after_mock_verification

这些测试覆盖执行成功、Mock record、平台请求/记录、伪造 DEVICE_EFFECT、验证工具失败、验证成功但效果层错误以及最终人工接管边界。

## 4. T0913 验收覆盖矩阵

| 验收项 | 代码/材料证据 | 结论 |
|---|---|---|
| 1. scope 唯一生产/消费 | ResponseEvidenceScopeResolver、ResponseDecisionService 相关单测和主链路径 | 通过 |
| 2. scope 实际传递 | Orchestrator.start() 调查后写入 TriageResult，决策生成 ResponsePlan.evidence_scope；Bridge/状态流测试 | 通过 |
| 3. 三份文档补齐 | 本目录 design.md、development.md、test.md | 本轮更新 |
| 4. 五层语义区分 | 领域模型、执行/验证测试；platform accepted 无独立证明 | 代码口径通过，真实平台能力未宣称 |
| 5. 四类 A/B 行为 | 20 份正式 OFF/GUARDED 报告及任务审查材料 | Investigation/knowledge 边界通过 |
| 6. CI/Review 候选 | 全量 pytest、git diff --check | 本地验证通过后可进入 PR 流程 |

## 5. 杨景凡正式 A/B 结果的证据边界

正式材料为 10 个案例的 OFF/GUARDED 共 20 份结果。已提供的证据可以支持：

- 强证据：case9 guarded knowledge 成功并产生知识引用，但报告仍有人工作业边界；
- 弱信号：case1、2、3、4、5、7、8 保持证据不足/人工接管口径；
- 域外事件：case6、case10 出现 knowledge_scope_mismatch；
- 工具失败：case5 记录 query_asset=failed，报告仍要求人工接管；
- 全部正式报告均为 need_manual_takeover=true，没有报告级可执行 WebShell ResponsePlan。

A/B 结果不能证明 response_evidence_scope 的 resolver 输入输出、ResponsePlan、真实平台执行、设备生效或独立验证。上述结论由代码测试单独验证，不能把 A/B 报告当作真实处置闭环证据。

## 6. 本轮测试命令与结果

执行目录：仓库根目录；Python 环境：仓库 .venv；测试入口：pytest。

命令：

~~~powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q -rs
~~~

本轮最终结果：

~~~text
383 passed, 1 skipped
~~~

跳过项是依赖 LLM_API_KEY 的真实 LLM 调查测试，不影响本地 Mock、scope 和处置闭环回归。

另执行：

~~~powershell
git diff --check
~~~

结果：通过，无空白错误。

## 7. 已知测试边界

- 没有真实平台受理回执的独立测试，因此当前系统不对 platform accepted 做独立证明。
- 没有真实设备状态变化和生产平台设备生效测试；DEVICE_EFFECT 场景是受控测试输入。
- A/B 材料没有 resolver/ResponsePlan/disposition 字段，不能替代代码级闭环测试。
- 当前不新增未知副作用状态、不改造 PATCH 接口、不测试超时/重试/回滚/持久化恢复和多动作部分成功。
- TRIAGED -> COMPLETED 的低风险分诊结束路径不作为响应处置完成证据。
