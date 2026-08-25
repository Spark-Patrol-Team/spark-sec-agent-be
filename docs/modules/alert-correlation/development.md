# 告警接入与关联模块开发说明

## 1. 代码位置与职责

| 代码位置 | 职责 |
|---|---|
| `src/sec_agent/platforms/raw_jsonl.py` | 读取原始 STA/XDR JSONL 并映射为 `NormalizedAlertRecord`。 |
| `src/sec_agent/platforms/jsonl_sample.py` | 在 `normalized` 或 `raw` 模式下读取固定样例，转换为 `AlertRecord`，提供证据查询 Mock 工具。 |
| `src/sec_agent/services/ingest.py` | 调用 `PlatformAdapter.fetch_alerts`，不承载字段映射。 |
| `src/sec_agent/services/correlation.py` | 基于类型、资产、设备和 15 分钟窗口执行最小关联，输出 `SecurityEvent`。 |
| `src/sec_agent/services/orchestrator.py` | 执行接入、关联、风险研判、调查、决策、审批、处置与验证的主链编排。 |
| `src/sec_agent/services/triage.py` | 基于 `SecurityEvent` 和参与关联的 `AlertRecord` 生成风险研判结果。 |
| `tests/test_alert_correlation_regression.py` | T0826-06 专项回归测试。 |

## 2. 输入模式与配置

```text
PLATFORM_BACKEND=jsonl_sample
JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts
JSONL_INPUT_MODE=normalized | raw
```

`normalized` 直接加载 `normalized_alerts.jsonl`，适用于固定契约回归；`raw` 加载 `raw_alerts.jsonl`，先通过 `RawJsonlNormalizer` 标准化再进入相同的 `AlertRecord` 适配路径。两种模式均不访问真实 XDR 平台。

本地 `.env` 不得提交。`.env.example` 只能保存不敏感的配置模板，不能出现真实账号、密码、Token、接入码或内部地址。

## 3. 本地调试

在仓库根目录执行以下命令。若外部环境设置了与项目不兼容的 `APP_ENV`，测试前应清除该外部变量或显式设置 `APP_ENV=local`。

```bash
# T0826-06 专项回归
PYTHONPATH=src python -m unittest tests.test_alert_correlation_regression

# JSONL 读取与标准化已有回归
PYTHONPATH=src python -m unittest \
  tests.test_raw_jsonl_ingest_and_correlation tests.test_jsonl_platform

# 全量测试
PYTHONPATH=src python -m unittest discover -s tests

# raw 固定 JSONL 最小主链
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample \
JSONL_INPUT_MODE=raw JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts \
PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

主流程脚本默认选取 `FIX-XDR-WEBSHELL-001`。执行后应先到达 `APPROVAL_REQUIRED`，脚本中的 Mock 审批通过后继续到 `COMPLETED`。该结果用于验证固定样例主链衔接，不证明真实处置动作已经执行。

## 4. 关键实现约束

### 4.1 字段映射

业务字段规则以 `tests/fixtures/fixed_alerts/raw_to_normalized_mapping.csv` 和固定 JSONL 为基线。`affected_asset` 必须优先取 `destination_ip`，仅在目的地址缺失时回退 `host_ip`；STA 与 XDR 的 `source_device_name` 映射不能混用。

`WebShell蚁剑工具文件管理` 的高危固定样例是专项覆盖：输出为 `critical/95`。通用 XDR 高危仍映射为 `high/80`，不得把专项规则扩大为全局高危升级。

### 4.2 关联边界

关联服务接收的是同一候选活动的 `AlertRecord` 列表，且不改变 `EventContext.status`。关联条件为：`alert_type` 一致、受影响资产一致、`source_device_name` 一致、首末时间跨度不超过 15 分钟。服务不实现跨资产、跨设备或跨场景的自动聚类。

### 4.3 证据可追溯性

`AlertRecord.evidence_refs` 保存标准化字段级证据引用；`raw_record_ref` 记录原始或标准化 JSONL 文件与样例 ID。`SecurityEvent.alert_refs` 保存参与关联的告警 ID，而调查阶段可通过平台适配器的 `evidence_lookup` 根据这些 ID 查询字段级证据。

真实 XDR OpenAPI/MCP 接入由平台工具入口另行实现。接入后应维持 `PlatformAdapter` 与 `AlertRecord` 契约，新增接口鉴权、超时、分页、限流、重试、脱敏与审计测试；不能用固定 JSONL 测试结果替代真实接口验证。
