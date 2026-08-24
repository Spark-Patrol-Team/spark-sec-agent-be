# 处置闭环模块开发说明

## 代码位置

- `src/sec_agent/services/response.py`
- `src/sec_agent/platforms/mock_state.py`
- `src/sec_agent/platforms/fixed_sample.py`
- `src/sec_agent/platforms/jsonl_sample.py`
- `src/sec_agent/services/orchestrator.py`

## 接入方式

由 `Orchestrator` 在深度调查完成并形成 `InvestigationReport` 后调用：

1. `ResponseDecisionService` 根据调查报告和上游 `TriageResult` 生成 `ResponsePlan`。
2. 高风险处置方案进入 `APPROVAL_REQUIRED`，等待审批结果。
3. 审批通过后，`ResponseExecutionService` 通过 `PlatformAdapter` 发起处置工具调用。
4. 执行成功后进入 `VERIFYING`，由 `ResponseVerificationService` 独立查询处置状态。
5. 根据查询结果进入 `COMPLETED`、`HUMAN_REQUIRED` 或 `FAILED`。

业务模块不直接推进业务状态，状态推进由 `Orchestrator` 和状态机统一完成。

## 当前 MVP 已实现

- 调查结果可以进入处置方案生成。
- 处置方案包含动作、目标、风险等级、审批要求和回滚可用性。
- 固定样例和 JSONL 样例均支持有状态 Mock 处置。
- 处置执行使用统一 `ToolRequest` / `ToolResult` 契约。
- 执行结果明确标记 `mode=mock`，不代表真实平台处置。
- 执行使用 `idempotency_key`，Mock 账本不会用同一幂等键覆盖已有记录。
- 执行后通过平台适配器查询处置状态，不能仅依据调用成功判断处置已经生效。
- 验证结果支持有效、无效和未知，并可分别进入完成或人工接管路径。

## Mock 实现边界

### 处置闭环 Mock

`src/sec_agent/platforms/mock_state.py` 中的 `StatefulMockLedger` 是处置专用状态账本：

- 使用 `idempotency_key` 标识一次处置请求；
- 保存 `action_status`、证据引用和结果摘要；
- 为执行结果和执行后验证提供同一份状态来源；
- 当前状态保存在进程内存中，服务重启后不会保留。

固定样例和 JSONL 适配器通过该账本实现：

```text
stateful_response_mock
  -> record_action()
  -> response_verify
  -> query_action_status()
```

### 通用工具 Mock

`src/sec_agent/tools/stateful_mock_tool.py` 是通用工具调度路径中的会话 Mock：

- 使用 `session_id` 隔离不同工具会话；
- 使用 `input_data` 合并会话状态；
- 使用 `idempotency_key` 避免同一工具请求重复写入；
- 不负责表达处置是否生效，也不替代处置专用账本。

## 尚未实现

- 真实平台处置工具接入。
- Mock 状态持久化。
- 处置回滚。
- 实际超时控制和自动重试。
- 更细粒度的部分成功和多动作处置结果。
- 风险分数与风险等级的最终团队统一规则。

