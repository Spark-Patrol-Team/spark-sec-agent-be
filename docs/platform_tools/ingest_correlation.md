# 告警读取、标准化与简单关联实现说明

## 目标与边界

本模块实现最小纵向链路的前两段：**固定告警读取 → 标准化为 `AlertRecord` → 简单关联为 `SecurityEvent`**。实现服务于 WebShell 主场景，同时保留 SQL 注入和横向移动固定样例作为回归输入。模块不修改编排器状态；`RECEIVED`、`CORRELATING` 等状态由 `src/sec_agent/services/orchestrator.py` 统一推进。

原始平台地址、账号、密码、Token、接入码、截图和原始 PCAP 均不进入仓库。固定样例仅使用 RFC 5737 文档保留地址，并始终保留 `sample_nature` 以区分 `platform_derived` 和 `synthetic_regression`。

## 代码落位

| 位置 | 职责 |
|---|---|
| `src/sec_agent/platforms/raw_jsonl.py` | 读取 `raw_alerts.jsonl`，执行 STA/XDR 字段映射并生成 `NormalizedAlertRecord`。 |
| `src/sec_agent/platforms/jsonl_sample.py` | 以 `normalized` 或 `raw` 输入模式读取样例，并转换为主链消费的 `AlertRecord`。 |
| `src/sec_agent/services/ingest.py` | 调用平台适配器，不重复处理来源字段。 |
| `src/sec_agent/services/correlation.py` | 在单次候选活动内压缩重复告警，输出 `SecurityEvent`。 |
| `tests/test_raw_jsonl_ingest_and_correlation.py` | 覆盖原始读取、映射一致性、回退、关联和最小主链输入。 |

## 原始读取与标准化规则

`JsonlSampleAdapter` 默认使用 `input_mode="normalized"`，直接读取 `normalized_alerts.jsonl`；设置 `input_mode="raw"` 后读取 `raw_alerts.jsonl`，调用 `RawJsonlNormalizer` 后进入相同 `AlertRecord` 转换逻辑。两种路径的 3 条固定样例标准化结果必须逐字段一致，唯一区别是原始输入路径会将 `raw_record_ref` 指向 `raw_alerts.jsonl`。

| 规则项 | 最终行为 |
|---|---|
| 时间 | `record_time` 或 `alert_time` 按 `Asia/Shanghai` 补齐时区，输出 ISO-8601 时间。 |
| 设备名称 | STA 优先取 `reporting_device_name`，XDR 优先取 `source_device_name`；缺失时依次回退来源设备字段和来源类型。 |
| 资产 | `affected_asset` 优先使用 `destination_ip`；仅当目的地址缺失时使用 `host_ip`。 |
| XDR 基础等级 | 严重/高危/中危/低危分别映射为 `critical`/`high`/`medium`/`low`。 |
| WebShell 专项覆盖 | `WebShell蚁剑工具文件管理` 且原始等级为高危时，固定映射为 `critical`，`risk_score_seed=95`。该规则不影响其他“高危”告警。 |
| 固定样例数据性质 | 保留 `platform_derived` 或 `synthetic_regression`，不允许合成样例伪装为实时平台数据。 |

## 简单关联规则

关联服务只处理由上层认定为同一候选攻击活动的一组告警。为了避免把无关告警合并，告警必须满足以下条件：事件类型一致、受影响资产一致、来源设备一致，且首末告警时间跨度不超过 15 分钟。若任一条件不满足，服务返回可读异常，由上层拆分为不同安全事件。

关联成功后输出一个 `SecurityEvent`，其中包含参与告警引用、首末发生时间、源/目的 IP、受影响资产、来源设备、关联依据、压缩前告警数、关联后事件数和面向后续研判的摘要。重复 WebShell 告警在 15 分钟内应产生 `alert_count_before=2` 和 `event_count_after=1`，用于前端和评测展示压缩效果。

## 运行方式

```bash
# 使用原始 JSONL 路径进行本轮最小纵向链路演示
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample JSONL_INPUT_MODE=raw \
PYTHONPATH=src python -m sec_agent.scripts.run_flow

# 运行陈敏模块测试和既有 JSONL 平台测试
PYTHONPATH=src python -m unittest \
  tests.test_raw_jsonl_ingest_and_correlation tests.test_jsonl_platform
```

主流程会以 `FIX-XDR-WEBSHELL-001` 启动，经过 `RECEIVED → CORRELATING → TRIAGED → INVESTIGATING → DECISION_READY → APPROVAL_REQUIRED`。演示脚本批准 Mock 处置后，流程进入 `EXECUTING → VERIFYING → COMPLETED`。真实 XDR OpenAPI/MCP 调用不在该固定样例降级路径中，须由可用平台适配器另行接入和验证。

## 验收结果口径

本轮验收以可重复运行和输入输出可追溯为准，不编造准确率、召回率等缺乏可靠标签的指标。最小验收包括：3 条原始样例与标准化样例完全一致；WebShell 专项规则保持 `critical/95`；通用高危映射保持 `high`；目的地址优先级正确；重复样例压缩为一个安全事件；原始输入路径可进入审批和验证完成状态。
