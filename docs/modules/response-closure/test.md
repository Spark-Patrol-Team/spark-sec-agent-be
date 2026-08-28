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

## 复测基线

本轮复测日期：2026-08-26。

- 当前分支：`test/response-closure-regression`
- 当前提交：`95defad`
- 当前 `HEAD`、本地 `main` 和 `origin/main` 指向同一提交；
- PR #16 合并提交：`36697e9`，是当前 `main` 的祖先；
- PR #14 合并提交：`7df76ca`，当前响应闭环相关测试在其后的主干上通过。

因此，本轮结论是：PR #14 的合并没有覆盖掉 PR #16 的响应闭环实现。PR #14 及后续主干对适配器、工具调度和编排幂等做过调整，已通过当前代码的回归测试确认核心行为仍然存在。

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

本轮 HTTP 黑盒复测中，首次审批和重复审批后的时间线长度均为 9。

### 审批拒绝

- 审批接口返回事件状态 `HUMAN_REQUIRED`；
- 不进入 `EXECUTING`；
- 不调用处置执行工具。

### 执行失败

使用故障平台替身使 `stateful_response_mock` 返回 `failed`：

- `ExecutionResult.executed` 为 `false`；
- 主流程进入 `FAILED`；
- 不继续进入执行后验证。

### 验证状态未知

使用故障平台替身使验证工具返回 `partial_success` 且 `action_status=not_found`：

- `VerificationResult.status` 为 `unknown`；
- 主流程进入 `HUMAN_REQUIRED`；
- 返回人工接管建议。

### 独立结果查询

- 执行后由 `response_verify` 查询 `StatefulMockLedger`；
- 成功记录的 `action_status` 为 `executed`；
- 查询结果包含 `fixed://actions/<idempotency_key>` 或 `jsonl://actions/<idempotency_key>` 证据引用；
- 验证不是直接复用执行接口的成功状态。

### 通用 Stateful Mock

- 相同 `session_id` 的多次调用会合并状态；
- 不同 `session_id` 的状态互相隔离；
- 相同 `idempotency_key` 的重复调用不会再次写入；
- `input_data` 非对象时返回结构化校验失败。
- 根目录旧工具测试已在提交 `91bc4d0` 迁移至 `tests/test_mvp_tool.py`；
- 迁移后的 Stateful Mock 等价覆盖仍保留，并纳入当前全量测试。

## 已执行验证

- 相关 `unittest`：26 个响应闭环相关测试通过，覆盖固定样例、JSONL 样例、审批、幂等、处置账本、通用 Stateful Mock、工具调度和契约检查。
- `tests/test_mvp_tool.py`：XDR 查询、通用 Stateful Mock 和不支持工具 3 个等价测试通过。
- 全量 `pytest`：73 个通过，1 个跳过。
- 全量 `unittest`：74 个测试通过，1 个跳过。
- 固定样例对象链路：审批、执行、状态查询、独立验证通过。
- JSONL WebShell 样例：风险分数 95，进入 `APPROVAL_REQUIRED`，审批后完成闭环。
- 编排故障分支：执行失败和验证未知均通过。
- HTTP 黑盒：`/health`、`/runs`、事件时间线、审批接口、重复审批、事件详情和 `/metrics` 通过。
- `git diff --check`：响应闭环相关变更无空白错误。

## 本轮测试结果记录

### 相关 unittest

执行命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_flow tests.test_tool_contract tests.test_tool_dispatcher_integration tests.test_investigation_and_dispatcher_integration tests.test_jsonl_platform tests.test_stateful_mock_tool -v
```

结果：

```text
Ran 26 tests in 0.040s
OK
```

### 全量 pytest

执行项目 CI 同款命令：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q -rs
```

结果：

```text
73 passed, 1 skipped in 0.87s
```

唯一跳过项是 `tests/test_investigation_agent.py` 中依赖 `LLM_API_KEY` 的真实 LLM 调查测试，不影响本地 Mock 和处置闭环回归。

### 全量 unittest

执行全量发现命令：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

结果：

```text
Ran 74 tests in 0.182s
OK (skipped=1)
```

### HTTP 黑盒结果

使用 `.venv\Scripts\uvicorn.exe` 启动本地服务后，实际请求结果：

```text
/health                         -> 200, status=ok
POST /runs                      -> 200, status=APPROVAL_REQUIRED
GET /events/<id>/timeline       -> 200, RECEIVED -> ... -> APPROVAL_REQUIRED
POST /events/<id>/approval      -> 200, status=COMPLETED
                                execution.status=success
                                verification.status=effective
                                verification.final_status=COMPLETED
重复 POST /approval             -> 200, status=COMPLETED, timeline_count=9
GET /events/<id>                -> 200, status=COMPLETED
GET /metrics                    -> 200, total_events=1, completed_events=1
```

## 尚未覆盖

- 真实平台处置动作。
- Mock 状态跨进程或重启后的持久化恢复。
- 实际超时控制和自动重试。
- 处置回滚。
- 多个处置动作的部分成功组合。
