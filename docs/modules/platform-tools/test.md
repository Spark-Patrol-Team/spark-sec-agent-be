# 平台工具模块测试记录

## 0. 复验信息

| 项目 | 内容 |
|---|---|
| 模块 | 平台工具模块（Platform Tools） |
| 任务/测试批次 | `T0827-05`；承接 `T0826-07` 复测结论 |
| 执行人 | 杨嘉琪 |
| 执行时间 | 2026-08-28（终端未单独记录具体时刻） |
| 基线分支与 Commit | `main@95defad5e6d8a44fdb601d844d876f25544f479d` |
| 环境 | Windows PowerShell；Python `3.13.9`；项目本地 `.venv`；`PYTHONPATH=src` |
| 数据集/样例版本 | 基线内置 XDR SQL 注入样例、固定/JSONL 样例及有状态 Mock；未使用真实平台数据 |
| 工作流/知识库版本 | 不适用；本轮验证工具调度器，不验证知识库内容 |
| 能力性质 | 自研调度代码、固定样例、Mock；未调用真实 XDR |
| 验收层级 | 模块集成与回归 |
| 总体结论 | 通过 |
| 关联正式交付章节 | 测试方案与测试报告的平台工具和调查工具链章节；具体章号待总文档负责人统一 |

## 1. 测试范围与不在范围内事项

### 1.1 本轮覆盖

- `ToolDispatcher` 对五类已注册工具的构建和调度。
- `evidence_lookup`、`stateful_response_mock` 和 `response_verify` 主流程调用。
- 调查链对 `xdr_log_query` 的调度调用。
- `xdr_log_query` 返回内置 XDR 样例记录。
- `stateful_mock` 对同一 session 的状态合并。
- 未知工具返回结构化错误。
- 未知工具的 `status=FAILED`、`error_type=UNSUPPORTED_TOOL`、`retryable=true`。

### 1.2 本轮未覆盖

- 最新主干完整 pytest 测试集。
- 真实 XDR 平台连接、鉴权、分页、限流和字段映射。
- 真实平台成功、空结果、401/403、429、超时和不可达响应。
- MCP、FastGPT/OpenClaw 等真实平台能力。
- 真实隔离、封禁、删除等有副作用动作。
- 前端到真实平台的完整端到端链路。

## 2. 前置条件与测试数据

- 前置条件：仓库位于基线 Commit；项目 `.venv` 可用；依赖已安装；从仓库根目录执行；`PYTHONPATH=src`。
- 测试数据性质：固定样例、JSONL 样例、人工构造请求和 Mock 状态。
- 测试数据位置：内置 XDR 记录位于 `src/sec_agent/tools/xdr_query_tool.py`；其他固定数据位于 `tests/fixtures/` 和平台样例适配器。
- 数据安全：本轮未使用真实平台凭据、未脱敏平台响应或客户真实数据。
- Windows 时区依赖：若缺少 IANA 时区数据，需要在项目 `.venv` 安装 `tzdata`。

## 3. 真实执行命令

从仓库根目录执行：

```powershell
git rev-parse HEAD
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_tool_dispatcher_integration.py tests/test_mvp_tool.py
```

实际基线输出：

```text
95defad5e6d8a44fdb601d844d876f25544f479d
```

实际 pytest 输出：

```text
......                                                               [100%]
6 passed in 0.13s
```

本轮没有执行完整 pytest，不能将以上结果表述为“最新主干全部测试通过”。

## 4. 测试用例与实际结果

| 用例 ID | 优先级 | 类型 | 场景/输入 | 预期结果 | 实际结果 | 状态 | `trace_id` | 证据编号 | 缺陷编号 |
|---|---|---|---|---|---|---|---|---|---|
| PT-T0827-001 | P0 | 正常/集成 | 调度主流程工具：证据查询、Mock 响应和响应验证 | 三类工具均由统一调度器执行并返回成功契约 | `test_dispatcher_runs_main_flow_tools` 通过 | Pass | 测试内构造 | EVID-T0827-001 | 无 |
| PT-T0827-002 | P0 | 正常/集成 | 调查链请求 `xdr_log_query` | 已注册并返回 `output_preview.records` | `test_dispatcher_supports_xdr_log_query_for_investigation_chain` 通过 | Pass | 测试内构造 | EVID-T0827-001 | 无 |
| PT-T0827-003 | P0 | 异常/集成 | 调用 `unknown_tool` | `FAILED / UNSUPPORTED_TOOL / retryable=true` | `test_dispatcher_returns_structured_error_for_unknown_tool` 通过 | Pass | 测试内构造 | EVID-T0827-001 | 无 |
| PT-T0827-004 | P0 | 正常/模块 | 调用 `xdr_log_query` | 返回一条内置 XDR 样例，状态成功且只读 | `test_xdr_log_query_returns_builtin_sample` 通过 | Pass | 测试内构造 | EVID-T0827-002 | 无 |
| PT-T0827-005 | P0 | 正常/模块 | 同一 session 连续调用 `stateful_mock` | 第二次结果保留并合并第一次状态 | `test_stateful_mock_merges_session_state` 通过 | Pass | 测试内构造 | EVID-T0827-002 | 无 |
| PT-T0827-006 | P0 | 异常/模块 | 调用未注册工具 | 返回结构化失败，不抛出未处理异常 | `test_unknown_tool_returns_structured_error` 通过 | Pass | 测试内构造 | EVID-T0827-002 | 无 |

正式用例状态均使用 `Pass`。测试框架没有 skipped 项。

## 5. 结果汇总

| 指标 | 数量 |
|---|---:|
| 通过 | 6 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 不适用 | 0 |
| 测试框架 skipped | 0 |

- 关键输出摘要：`6 passed in 0.13s`。
- 实际调用的工具：`evidence_lookup`、`xdr_log_query`、`stateful_mock`、`stateful_response_mock`、`response_verify` 及未知工具错误分支。
- 实际使用的数据能力：固定样例、内置 XDR 样例和 Mock；未调用真实平台。
- 与预期不一致项：无。

## 6. 指标贡献与原始计数

| 指标 | 计算口径 | 分子/原始计数 | 分母/原始计数 | 结果 | 数据或脚本证据 |
|---|---|---:|---:|---:|---|
| 目标用例通过率 | 两份指定测试文件中通过用例数 / 执行用例数 | 6 | 6 | 100% | EVID-T0827-003 |
| 目标测试失败率 | 失败用例数 / 执行用例数 | 0 | 6 | 0% | EVID-T0827-003 |
| 已验证工具注册覆盖 | 已验证注册和调度的目标工具数 / 本轮目标工具数 | 5 | 5 | 100% | EVID-T0827-001、EVID-T0827-002 |
| 未知工具契约通过率 | 通过的未知工具结构化错误用例 / 执行的对应用例 | 2 | 2 | 100% | EVID-T0827-001、EVID-T0827-002 |

以上指标只反映两份目标测试，不代表真实平台准确率、全链路成功率或最新主干全部测试通过率。

## 7. 证据索引

| 证据 | 位置 | 脱敏状态 | 支持的结论 |
|---|---|---|---|
| EVID-T0827-001 | `tests/test_tool_dispatcher_integration.py` | 不含敏感信息 | 主流程工具、XDR 调查链和未知工具错误契约 |
| EVID-T0827-002 | `tests/test_mvp_tool.py` | 不含敏感信息 | 内置 XDR、状态合并和未知工具错误契约 |
| EVID-T0827-003 | 本文第 3 节记录的终端命令与输出 | 不含敏感信息 | 基线 Commit 和 `6 passed in 0.13s` |
| EVID-T0827-004 | `src/sec_agent/tools/base.py`、`tool_dispatcher.py` | 不含敏感信息 | 唯一调度器、五类注册和 `extra_handlers` 扩展点 |
| EVID-T0827-005 | `src/sec_agent/tools/xdr_query_tool.py` | 不含敏感信息 | 当前 XDR 能力为内置样例和只读返回 |

原始平台截图、真实返回、STA 接入码、Token、真实 MCP URL 和内网地址不进入本文或 GitHub。

## 8. 失败项与已知限制

| 问题 | 复现方式 | 影响 | 当前处理/下一步 |
|---|---|---|---|
| Windows 缺少 `tzdata` | 在缺少 IANA 时区数据的 Windows `.venv` 加载 `Asia/Shanghai` | 局部影响本地测试，不阻塞 Linux 主链 | 执行 `.\.venv\Scripts\python.exe -m pip install tzdata` |
| `xdr_log_query` 当前为内置固定样例 | 调用默认 handler | 不阻塞固定样例主链；无法证明真实 XDR 已接通 | 获得真实接口、权限、鉴权和脱敏样例后实现 adapter |
| 本轮未执行完整 pytest | 仅执行两份指定测试文件 | 不能推导全部主干测试状态 | 由主干收口负责人执行完整测试并冻结候选 Commit |
| 真实平台异常分支未测试 | 当前无真实平台测试环境和响应样例 | 不阻塞样例主链；阻塞真实接入验收 | 平台条件就绪后补鉴权、超时、限流、不可达和空结果测试 |

本轮没有业务代码失败项，不登记业务缺陷。

## 9. 验收结论

- 本轮可确认：基线 `95defad5e6d8a44fdb601d844d876f25544f479d` 上，两份指定测试文件共 6 项用例全部通过。
- 本轮可确认：五类工具已注册并可由统一 `ToolDispatcher` 调度。
- 本轮可确认：未知工具返回 `FAILED / UNSUPPORTED_TOOL / retryable=true`。
- 本轮可确认：默认 `xdr_log_query` 返回内置 SQL 注入样例，属于只读固定样例能力。
- 本轮不能确认：真实 XDR API 已接通、真实字段已映射或真实平台错误处理已经实测。
- 是否影响上下游或主链：不影响当前固定样例主链；真实平台接入仍受权限、接口、鉴权和脱敏样例阻塞。
- 建议状态：当前平台工具固定样例模块 `已验收`；真实 XDR 只读能力为 `已提交准备说明，待平台条件就绪`。

## 10. 变更记录

| 日期 | 基线 Commit | 新增或变更测试 | 结论 |
|---|---|---|---|
| 2026-08-26 | `5defad5e6d8a44fdb601d844d876f25544f479d` | `T0826-07`：两份目标测试、五类工具和未知工具错误复测 | 通过；Windows `tzdata` 为本地环境问题 |
| 2026-08-28 | `95defad5e6d8a44fdb601d844d876f25544f479d` | `T0827-05`：在冻结基线上复跑两份目标测试，并补真实 XDR 就绪边界 | 6 passed，0 skipped，0 failed |

