# 告警读取、标准化与简单关联测试报告

## 测试范围

本报告记录“固定告警读取 → 标准化 → 简单关联”最小实现验证结果。测试仅使用仓库 `tests/fixtures/fixed_alerts/` 中的脱敏 JSONL。

## 执行环境与命令

测试在 Python 3.12 隔离环境执行。原始 JSONL 主流程运行时显式设置本地内存配置。

```bash
# 新增测试与既有 JSONL 平台测试
PYTHONPATH=src python3 -m unittest \
  tests.test_raw_jsonl_ingest_and_correlation tests.test_jsonl_platform

# 全量后端测试，避免环境变量干扰配置测试
env -u APP_ENV -u APP_NAME -u PLATFORM_BACKEND -u JSONL_INPUT_MODE \
  -u JSONL_SAMPLE_DIR -u STORAGE_BACKEND \
  PYTHONPATH=src python3 -m unittest discover -s tests

# 原始 JSONL 降级路径主流程
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample \
JSONL_INPUT_MODE=raw JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts \
PYTHONPATH=src python3 -m sec_agent.scripts.run_flow
```

## 测试结果

| 编号 | 验证项 | 实际结果 | 结论 |
|---|---|---|---|
| R-01 | 原始 JSONL 标准化与已提交标准化样例逐字段对比 | 3 条记录一致。 | 通过。 |
| R-02 | WebShell 专项覆盖规则 | `FIX-XDR-WEBSHELL-001` 输出 `severity=critical`、`risk_score_seed=95`、`affected_asset=198.51.100.11`。 | 通过。 |
| R-03 | 通用高危与资产回退 | 非蚁剑 WebShell 高危变体保持 `high/80`；当 `destination_ip` 缺失时才使用 `host_ip`。 | 通过。 |
| R-04 | AlertRecord 证据定位 | 原始输入路径生成 `jsonl://fixed_alerts/raw_alerts.jsonl#<sample_id>`。 | 通过。 |
| R-05 | 重复告警压缩 | 两条 2 分钟内的同场景 WebShell 告警压缩为一个事件，`2 → 1`。 | 通过。 |
| R-06 | 无关告警保护 | 不同事件类型不能在单次简单关联中合并，返回可读拆分异常。 | 通过。 |
| R-07 | 原始输入最小主链 | WebShell 样例经审批 Mock 处置后到达 `COMPLETED`。 | 通过。 |
| R-08 | 新增与既有 JSONL 测试 | 12 个测试全部通过。 | 通过。 |
| R-09 | 后端完整测试集 | 26 个测试全部通过。 | 通过。 |

## 主流程实测状态

原始 WebShell 样例启动后依次产生 `RECEIVED`、`CORRELATING`、`TRIAGED`、`INVESTIGATING`、`DECISION_READY` 和 `APPROVAL_REQUIRED`。演示审批通过后，状态继续推进至 `EXECUTING`、`VERIFYING` 和 `COMPLETED`。该结果证明陈敏模块输出可以被现有风险研判、调查、Mock 处置和独立验证链路消费。

## 已知边界与协作项

本模块完成的是固定样例降级路径，不替代真实 XDR OpenAPI/MCP 的鉴权、拉取和字段映射。后端在冻结 `AlertRecord` 与编排接口时，应合并本模块新增的 `raw` 输入模式、`SecurityEvent` 关联依据及测试；获取真实平台工具入口可在保持 `PlatformAdapter` 契约不变的前提下替换固定样例适配器。风险研判、调查、处置和前端负责人可直接消费 `AlertRecord`、`SecurityEvent` 及其证据引用，不需要复制中间 JSON。
