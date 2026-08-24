# 处置闭环模块测试说明

## 测试范围

- 生成处置方案。
- 高风险动作进入审批。
- 审批通过后执行。
- 审批拒绝后人工接管。
- 执行后验证。
- 重复审批幂等。
- Mock 状态查询。
- 执行失败和验证状态未知。

## 已验证场景

### 固定样例成功闭环

输入：

```json
{
  "source": "fixed_sample",
  "sample_id": "webshell-001"
}
```

预期状态线：

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

已确认结果：

- 调查报告包含处置建议；
- 处置方案能够生成并等待审批；
- 审批通过后执行结果为成功；
- 执行模式为 `mock`；
- 独立查询能够返回 `executed`；
- 验证状态为 `effective`；
- 最终业务状态为 `COMPLETED`。

### 重复审批

使用相同的审批 `idempotency_key` 重复提交：

- 返回结果保持已完成状态；
- 不新增 `EXECUTING`、`VERIFYING` 或 `COMPLETED` 时间线；
- 不重复推进主流程。

### 执行失败

当执行工具返回失败时：

- `ExecutionResult.executed` 为 `false`；
- 主流程进入 `FAILED`；
- 不继续进入执行后验证。

### 验证状态未知

当验证工具找不到处置记录或只能返回部分结果时：

- `VerificationResult.status` 为 `unknown`；
- 主流程进入 `HUMAN_REQUIRED`；
- 返回人工接管建议。

## 已执行验证

- `tests/` 下的 `unittest`：30 个测试通过。
- `test_mvp_tool.py`：XDR 查询、通用 Stateful Mock 和不支持工具分支通过。
- 固定样例对象链路：审批、执行、状态查询、独立验证通过。
- HTTP 接口：`/runs`、审批接口、事件详情、时间线、事件列表和指标接口通过。

## 尚未覆盖

- 真实平台处置动作。
- Mock 状态跨进程或重启后的持久化恢复。
- 实际超时控制和自动重试。
- 处置回滚。
- 多个处置动作的部分成功组合。

