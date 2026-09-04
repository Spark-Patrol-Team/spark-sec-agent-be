# 处置闭环模块设计

## 1. 设计目标

处置闭环模块负责承接调查结论，生成处置方案，完成风险分级、审批门禁、执行协调和独立验证。

当前实现的闭环动作仍是 `stateful_mock_containment`，它只用于本地演示和回归验证，不代表真实平台已经完成封禁、隔离、阻断或其他高风险动作。

## 2. 分层口径

为避免把不同层级混写，本文档统一按以下口径表述：

- `L0`：页面、列表、日志、配置和查询等可见能力，仅证明“能看见”；
- `Mock`：本地有状态 Mock 和单测回归，仅证明“流程可跑通”；
- `平台记录`：平台内产生了执行记录、审计记录或动作回执，仅证明“平台留痕”；
- `设备生效`：真实网络、主机或文件状态已经发生变化，仅能在可验证对象和有效证据下确认；
- `外部阻塞`：当前缺少真实设备、真实接口、授权对象或独立验证条件，导致真实动作暂不可确认。

后续涉及“已确认”或“未确认”的表述，均应按上述层级区分，不能互相替代。

## 3. 输入输出

- 输入：`InvestigationReport`、`TriageResult`、审批结果；
- 输出：`ResponseResult`，包含处置方案、执行结果和验证结果。

`ResponseDecisionService` 只有在以下条件同时满足时才生成处置方案：

- 调查没有要求人工接管；
- 调查报告包含处置建议；
- 调查报告包含明确的受影响对象。

当前方案字段为：

- 动作：`stateful_mock_containment`；
- 目标：调查报告中的第一个 `affected_objects`；
- 风险等级：根据 `TriageResult.risk_score` 确定；
- 回滚可用性：当前固定为 `true`，但实际回滚动作尚未实现。

## 4. 风险与审批

当前响应模块内的风险等级阈值为：

- `risk_score >= 90`：`critical`；
- `70 <= risk_score < 90`：`high`；
- `40 <= risk_score < 70`：`medium`；
- `risk_score < 40`：`low`。

`medium`、`high`、`critical` 方案需要人工审批；审批通过后才进入执行。审批拒绝后进入 `HUMAN_REQUIRED`，不会调用处置工具。

上述阈值是当前 MVP 的代码实现，不等同于团队最终风险评分规范；最终规则仍待团队确认。

## 5. 状态流转

正常闭环：

```text
RECEIVED
-> CORRELATING
-> TRIAGED
-> INVESTIGATING
-> DECISION_READY
-> APPROVAL_REQUIRED
-> EXECUTING
-> VERIFYING
-> COMPLETED
```

异常结果：

```text
审批拒绝或证据不足 -> HUMAN_REQUIRED
执行工具失败       -> FAILED
验证结果未知       -> HUMAN_REQUIRED
验证确认未生效     -> HUMAN_REQUIRED
```

业务状态由 `Orchestrator` 调用统一状态机推进，响应服务不直接修改主流程状态。

## 6. 安全边界

- 当前处置调用统一 `ToolRequest` / `ToolResult` 契约；
- 高风险方案必须经过人工审批；
- 执行结果成功不能直接等同于处置生效；
- 执行成功后必须通过 `response_verify` 独立查询；
- 真实平台处置能力尚未接入，当前执行结果必须标记为 `mode=mock`；
- 未获得明确授权时，不执行真实环境中的封禁、隔离或其他高风险动作。

## 7. Stateful Mock 边界

`StatefulMockLedger` 是处置专用的进程内状态账本，固定样例和 JSONL 样例适配器各自持有一个账本：

- 使用 `idempotency_key` 标识一次处置请求；
- 首次写入后不使用同一幂等键覆盖已有记录；
- 保存 `action_status`、证据引用、结果摘要和输出预览；
- 执行工具和验证工具读取同一份记录；
- 记录状态为 `executed` 时，独立验证返回 `effective`；
- 找不到记录时，工具返回 `partial_success` 和 `action_status=not_found`，编排结果为 `unknown -> HUMAN_REQUIRED`；
- 状态只保存在当前进程内，服务重启后不会保留。

通用 `stateful_mock` 使用独立的会话状态 `SESSION_STATE`：

- 使用 `session_id` 隔离会话；
- 使用 `input_data` 合并会话字段；
- 使用 `idempotency_key` 避免重复写入；
- 不负责表达处置动作是否生效，不能替代处置专用账本。

## 8. 当前实现与未实现

已实现：

- 处置方案生成和明确目标检查；
- 风险等级和审批门禁；
- 固定样例、JSONL 样例的有状态 Mock 执行；
- 处置执行后的独立状态查询；
- 验证服务对 `effective`、`ineffective`、`unknown` 三类结果的分支处理；
- 重复审批幂等；
- 执行失败、验证未知和人工接管状态。

当前内置处置 Mock 的标准路径会产生 `executed` 或 `not_found` 查询结果；`ineffective` 分支已在验证服务中定义，但尚未提供标准 Mock 接口注入 `action_status=failed` 的测试入口。

尚未实现：

- 真实平台处置工具接入；
- Mock 状态持久化；
- 实际超时控制和自动重试；
- 处置回滚；
- 多动作处置和部分成功组合；
- 最终统一的风险评分、审批和验证规则。

