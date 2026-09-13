# 处置闭环模块开发说明

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | response-closure |
| 本轮任务 | T0913：最终响应闭环完善、语义验收与交付准备 |
| 文档职责 | 实际代码位置、调用链、运行时实现、执行与验证流程 |
| 当前能力 | 本地 Stateful Mock 闭环；真实平台设备生效未验证 |

## 1. 代码位置

| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| src/sec_agent/services/orchestrator.py | Orchestrator.start()、approve()、_execute_and_verify() | 编排调查、范围冻结、决策、审批、执行、验证和最终状态 |
| src/sec_agent/services/response.py | ResponseEvidenceScopeResolver | 唯一生产 response_evidence_scope |
| src/sec_agent/services/response.py | ResponseDecisionService | 消费已冻结 scope，生成 ResponsePlan |
| src/sec_agent/services/response.py | ResponseExecutionService | 构造 ToolRequest 并调用平台工具 |
| src/sec_agent/services/response.py | ResponseVerificationService | 调用 response_verify 并判定验证结果 |
| src/sec_agent/services/investigation.py | DeepInvestigationAgent | 调查工具调用和 InvestigationStep.tool_result 记录 |
| src/sec_agent/services/deep_agent_bridge.py | DeepAgentBridge | 将 deep-agent 工具记录映射为领域调查步骤和结果 |
| src/sec_agent/domain/models.py | TriageResult、ResponsePlan、ExecutionResult、VerificationResult | 闭环领域数据模型 |
| src/sec_agent/platforms/base.py | PlatformAdapter | run_tool() 与 query_action_status() 平台抽象 |
| src/sec_agent/platforms/fixed_sample.py、jsonl_sample.py | 平台适配器 | 注册工具调度器和处置专用 Mock ledger |
| src/sec_agent/platforms/mock_state.py | StatefulMockLedger | 进程内处置记录、幂等和状态查询 |

## 2. 实际主链调用路径

实际运行关系不是由类名推断，而是由 Orchestrator 的调用顺序形成：

~~~text
Orchestrator.start()
  -> AlertIngestService / AlertCorrelationService / RiskTriageService
  -> DeepInvestigationAgent.investigate()
       -> tool chain / DeepAgentBridge
       -> InvestigationStep.tool_result
       -> InvestigationReport
  -> ResponseEvidenceScopeResolver.resolve()
       -> ctx.triage.response_evidence_scope
  -> ResponseDecisionService.build_plan()
       -> ResponsePlan.evidence_scope
  -> DECISION_READY / APPROVAL_REQUIRED
  -> Orchestrator.approve()
  -> Orchestrator._execute_and_verify()
  -> ResponseExecutionService.execute()
       -> ToolRequest(stage=EXECUTING)
       -> platform.run_tool("stateful_response_mock")
       -> ToolResult
       -> ExecutionResult
  -> ResponseVerificationService.verify()
       -> ToolRequest(stage=VERIFYING, tool_name="response_verify")
       -> platform.run_tool("response_verify")
       -> VerificationResult
  -> StateMachine.move(..., verification.final_status)
       -> final disposition
~~~

调查工具失败会进入调查报告的工具结果/调查缺口；主链随后由 resolver 和决策层按 fail-closed 规则阻止不安全升级。tool_call_records 在 Bridge 中映射到 InvestigationStep.tool_result，因此调查结果能够进入 scope 生产输入，而不是只停留在模型字段或原始 Agent 输出中。

## 3. Scope 的运行时传递

1. DeepInvestigationAgent 产出 InvestigationReport，其中包含步骤、工具结果、证据引用和未决问题。
2. Orchestrator.start() 调用唯一的 ResponseEvidenceScopeResolver.resolve(report, triage, event)。
3. resolver 返回的枚举值写入同一个 TriageResult.response_evidence_scope，并保存到事件上下文。
4. ResponseDecisionService.build_plan() 调用 _boundary_decision()，只读取 triage.response_evidence_scope。
5. 成功生成的 ResponsePlan.evidence_scope 保存该冻结值，供后续审批、执行和审查使用。

决策层对调查缺口、未决问题和工具失败的检查只用于一致性校验和收紧权限，不重新计算 scope。gate_decision、knowledge refs 和报告建议均不能绕过这条传递路径。

## 4. 执行与验证流程

### 4.1 方案与审批

ResponseDecisionService 先检查人工接管标志、建议动作和目标对象，再检查 scope、恶意结论、调查缺口和风险上限。当前动作固定为 stateful_mock_containment；中、高、严重风险需要审批。

Orchestrator.approve() 只接受 APPROVAL_REQUIRED 状态，使用审批幂等键避免重复推进。审批拒绝直接进入 HUMAN_REQUIRED，不调用处置工具。

### 4.2 执行

ResponseExecutionService.execute() 构造 ToolRequest，设置已批准状态、幂等键和 stage=EXECUTING，调用 PlatformAdapter.run_tool()。当前适配器将请求交给 stateful_response_mock，并由 StatefulMockLedger 写入进程内记录。

ToolResult.status=success 映射为 ExecutionResult.executed=true，但 ExecutionResult.effect_layer 仍为 STATEFUL_MOCK。执行失败映射为 executed=false，编排进入 FAILED，不继续验证。

### 4.3 独立验证

执行成功后，编排进入 VERIFYING。ResponseVerificationService 重新构造只读 ToolRequest 调用 response_verify，查询处置账本，而不是复用执行调用的成功状态。

只有以下条件同时满足才返回 VerificationResult.final_status=COMPLETED：

- 验证工具 ToolResult.status=success；
- 验证动作状态为 effective 或 executed；
- verified_effect_layer=DEVICE_EFFECT；
- 验证状态为 effective。

验证工具失败、部分成功、not_found、未知状态、failed/ineffective 或缺少 DEVICE_EFFECT 时，验证结果进入 HUMAN_REQUIRED，不会自动完成。

## 5. 五层状态在运行时的实际来源

| 层级 | 运行时来源 | 当前口径 |
|---|---|---|
| request sent | ToolRequest 创建并传入 platform.run_tool() | 只能证明系统发起调用 |
| platform accepted | 无独立字段、无独立平台回执契约 | 当前系统不对 platform accepted 做独立证明 |
| platform recorded | ToolResult.output_preview、Mock ledger 查询结果 | 只能证明存在记录/回执 |
| device effective | 验证输出中的 effect_layer=DEVICE_EFFECT | 当前由测试替身提供可控输入 |
| independent verification successful | response_verify 成功 + 有效动作状态 + DEVICE_EFFECT | 是进入响应 COMPLETED 的组合门槛 |

当前真实平台没有被现有测试证明能提供后四层中的独立受理、记录或设备效果证据。

## 6. 运行边界

- timeout_seconds=30 和 max_attempts=1 会写入请求，但本轮不实现实际超时调度或重试。
- Mock ledger 为进程内状态，不承担跨进程或重启恢复。
- 当前方案只执行一个固定 Mock 动作和第一个目标。
- rollback_available 是方案字段，不代表已实现回滚。
- 真实平台适配器、真实设备联动和生产级独立验证不在当前实现能力内。
- 本轮不新增未知副作用状态、不改造 PATCH 状态更新接口、不建立新的响应状态机。
