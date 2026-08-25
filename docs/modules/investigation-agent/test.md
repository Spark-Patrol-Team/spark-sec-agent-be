# 深度调查 Agent 模块测试说明

## 测试范围

- 数据模型：`SecurityEventInput` / `InvestigationReport` 序列化与往返。
- Mock 工具：命中 / 未命中 / 未知工具 / 注册数量。
- Agent 辅助逻辑：JSON 提取（含代码块围栏、噪声）、降级报告。
- 集成测试：完整 WebShell 调查闭环（需 LLM key，未配置时跳过）。

## 测试案例

| 用例 | 验证点 |
|------|--------|
| `test_event_roundtrip` | 事件模型 `from_dict` / `to_dict` 往返一致 |
| `test_report_serializable` | 报告可 JSON 序列化 |
| `test_asset_query_hit` | `query_asset` 命中 OA 服务器 |
| `test_asset_query_miss` | 未知 IP 返回 `failed`（数据不可得） |
| `test_unknown_tool` | 未知工具返回 `failed` |
| `test_mock_tools_registered` | 注册至少 6 个 Mock 工具 |
| `test_extract_json_plain` | 纯 JSON 提取 |
| `test_extract_json_fenced` | 带代码块围栏的 JSON 提取 |
| `test_extract_json_with_noise` | 带噪声文本的 JSON 提取 |
| `test_safe_json_loads` | 非法 JSON 兜底为空 dict |
| `test_fallback_report` | 证据不足 → 人工接管 |
| `test_ascii_tool_keeps_name` | ASCII 工具名别名＝真实名，不变更 |
| `test_chinese_tool_aliased_and_resolved` | 中文工具名映射内部别名，可解析还原真实名 |
| `test_unknown_tool_still_fails` | 未收录的中文工具名解析失败（不静默放行） |
| `test_alias_map_consistency` | `ALIAS_MAP` 值均为 ASCII 且与真实名对应 |
| `test_mock_schemas_ascii_unique` | Mock 工具 schema 全部 ASCII 且不重复 |
| `test_web_shell_full_run` | 完整 WebShell 调查（需 LLM key） |

## 执行方法

```bash
# 推荐（pytest）
PYTHONPATH=src python -m pytest tests/test_investigation_agent.py -q

# 或无需 pytest
PYTHONPATH=src python -m unittest tests.test_investigation_agent -v
```

## 结果

- 单元测试 16 项通过、1 项跳过（合计 17，均不依赖 LLM）。
- 集成测试 `test_web_shell_full_run` 需配置 `LLM_API_KEY`，未配置时跳过。

## 复验记录（2026-08-25，main + Mock）

- 在最新 main（含 PR #13）上运行：**16 passed / 1 skipped**，与开发分支一致。
- 独立运行 `sec_agent.deep_agent`（Mock 完整一轮，配置 LLM key）：6 个 Mock 工具、7 次工具调用、完整结构化报告、**实际调用 LLM**、**未发生内部 fallback**。
- 主链桥接集成测试 `tests/test_investigation_and_dispatcher_integration.py`：**5 passed**（新增 `test_bridge_loads_real_deep_agent_modules` 回归用例，验证 bridge 能从 `sec_agent.deep_agent` 加载真实模块；修复前该用例必挂）。
- 主链实测（`run_flow.py`，`auto` 后端）：补装 `tzdata` + 修复 bridge 导入路径后，**真实加载 PR #13 Agent + 实际调用 LLM + 7 次 Mock 工具调用**，生成完整结构化报告、未发生内部 fallback；WebShell 样例下报告标记人工接管 → 主链停在 HUMAN_REQUIRED（修复前回退子链会直接自动处置至 COMPLETED）。
- 环境备注：Windows Python 缺 `tzdata` 时主链 import 即报 `ZoneInfoNotFoundError: Asia/Shanghai`；`fastapi` / `sqlalchemy` / `pymysql` 为主链全链依赖。

## 样例数据性质

- `tests/fixtures/investigation/sample_event.json`：人工构造的 WebShell 固定样例（Mock），非真实平台数据。
- `src/sec_agent/deep_agent/tools/mock.py` 内置数据：人工构造，仅用于演示调查闭环。

## 已知问题

- 集成测试依赖真实 LLM 接口，本地未配置 key 时跳过。
- 尚未覆盖多步调查、外部 Agent 返回格式错误、工具超时等边界案例。
