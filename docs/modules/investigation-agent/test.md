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
| `test_web_shell_full_run` | 完整 WebShell 调查（需 LLM key） |

## 执行方法

```bash
python -m unittest test.test_agent -v
```

## 结果

- 单元测试 11 项全部通过（不依赖 LLM）。
- 集成测试 `test_web_shell_full_run` 需配置 `LLM_API_KEY`，未配置时跳过。

## 样例数据性质

- `test/sample_event.json`：人工构造的 WebShell 固定样例（Mock），非真实平台数据。
- `deep_agent/tools/mock.py` 内置数据：人工构造，仅用于演示调查闭环。

## 已知问题

- 集成测试依赖真实 LLM 接口，本地未配置 key 时跳过。
- 尚未覆盖多步调查、外部 Agent 返回格式错误、工具超时等边界案例。
