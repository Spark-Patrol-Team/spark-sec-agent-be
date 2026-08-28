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
3. 审批通过后，`ResponseExecutionService` 通过 `PlatformAdapter.run_tool()` 发起 `stateful_response_mock` 调用。
4. 执行成功后进入 `VERIFYING`，由 `ResponseVerificationService` 通过 `response_verify` 独立查询处置状态。
5. 根据执行和查询结果进入 `COMPLETED`、`HUMAN_REQUIRED` 或 `FAILED`。

业务模块不直接推进业务状态，状态推进由 `Orchestrator` 和状态机统一完成。

## 工具调用链

固定样例和 JSONL 样例适配器都通过 `build_platform_tool_dispatcher()` 注册以下工具：

```text
evidence_lookup
xdr_log_query
stateful_response_mock
response_verify
stateful_mock
```

处置闭环只使用其中的：

```text
stateful_response_mock
  -> StatefulMockLedger.record_action()
response_verify
  -> StatefulMockLedger.query_action_status()
  -> StatefulMockLedger.get()
```

## 幂等与状态

- `Orchestrator.approve()` 先通过仓库的 `claim_idempotency_key()` 抢占审批幂等键；
- 同一审批幂等键重复提交时直接返回当前事件，不重复推进主流程；
- `StatefulMockLedger.record_action()` 对同一处置幂等键只保留首次记录；
- 处置账本和通用 `stateful_mock` 的状态空间相互独立；
- 当前内存仓库和处置账本都不提供跨进程、跨重启恢复。

## 结果处理

### 执行成功

`ResponseExecutionService` 将 `ToolResult.status == success` 映射为：

```text
ExecutionResult.executed = true
ExecutionResult.mode = mock
```

随后必须进入 `VERIFYING`，不能直接结束为 `COMPLETED`。

### 执行失败

当处置工具返回非 `success`：

- `ExecutionResult.executed = false`；
- 主流程进入 `FAILED`；
- 不调用执行后验证；
- 当前实现不会自动重试。

### 验证结果

验证服务读取独立查询返回的 `action_status`：

- `executed`：`effective -> COMPLETED`；
- `failed`：`ineffective -> HUMAN_REQUIRED`；
- `not_found` 或其他无法确认状态：`unknown -> HUMAN_REQUIRED`。

## 当前实现边界

- `timeout_seconds=30` 和 `max_attempts=1` 会写入 `ToolRequest`，但当前没有真正的超时控制和重试调度；
- `rollback_available=true` 只是方案字段，实际回滚动作尚未实现；
- 当前每个方案只执行第一个目标和一个固定 Mock 动作；
- 固定样例和 JSONL 样例的状态账本均为进程内存；
- 真实平台、真实副作用、持久化恢复和多动作部分成功尚未接入。

