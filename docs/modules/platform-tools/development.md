# 平台工具模块开发说明 (T0828-06 真实字段映射)

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | `platform-tools`（平台工具） |
| 负责人 | 陈敏 |
| 实现状态 | 真实 XDR 接入已打通；支持 auth_code 签名；已验证 8 条真实数据。 |
| 基线方案 | 《2026年8月29日真实XDR告警输入接入解决方案》 |
| 最后更新时间 | 2026-08-29 |

---

> 以下内容完整保留自 PR #17 告警接入与关联开发说明。

## 1. 当前实现摘要

### 1.1 已实现
- `JsonlSampleAdapter` 在 `normalized` 模式下读取标准化固定样例，在 `raw` 模式下读取原始 JSONL 并调用 `RawJsonlNormalizer`。
- 原始样例可映射为 `NormalizedAlertRecord`，再适配为统一 `AlertRecord`。
- 固定映射支持 STA/XDR 来源设备、目的资产优先、`host_ip` 回退、WebShell 蚁剑专项 `critical/95` 与字段级证据引用。
- `AlertCorrelationService` 对同一候选活动执行事件类型、资产、来源设备和 15 分钟窗口校验，并输出 `SecurityEvent`。
- `Orchestrator` 在关联后调用风险研判；raw WebShell 固定样例可实际进入 `TRIAGED`、`APPROVAL_REQUIRED`，Mock 审批后到 `COMPLETED`。

### 1.2 未实现或未复验
- 真实 XDR OpenAPI/MCP 鉴权、实时查询、分页、限流、网络超时、重试和返回字段映射未实现。

## 2. 代码位置
| 路径 | 主要对象/入口 | 作用 |
|---|---|---|
| `src/sec_agent/platforms/raw_jsonl.py` | `RawJsonlNormalizer` | 原始 STA/XDR JSONL 到 `NormalizedAlertRecord` 的映射与校验。 |
| `src/sec_agent/platforms/jsonl_sample.py` | `JsonlSampleAdapter` | 读取 raw/normalized 固定样例，生成 `AlertRecord`，提供证据查询 Mock。 |
| `src/sec_agent/services/ingest.py` | `AlertIngestService.ingest` | 按来源调用平台适配器；不重复解析来源字段。 |
| `src/sec_agent/services/correlation.py` | `AlertCorrelationService.correlate` | 执行最小关联、实体汇总和关联依据生成。 |
| `src/sec_agent/services/orchestrator.py` | `Orchestrator.start` | 接入→关联→风险研判→调查→处置的统一状态编排。 |

## 3. 依赖与配置
- `PLATFORM_BACKEND=jsonl_sample`：运行固定 JSONL 主链时必需。
- `JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts`：运行固定 JSONL 时必需。
- `JSONL_INPUT_MODE=normalized|raw`：运行 JSONL 时可选。

## 4. 启动与调试
```bash
# raw 固定 JSONL 主链
APP_ENV=local STORAGE_BACKEND=memory PLATFORM_BACKEND=jsonl_sample \
JSONL_INPUT_MODE=raw JSONL_SAMPLE_DIR=tests/fixtures/fixed_alerts \
PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

---

## 11. 8 月 29 日真实接入实现细节 (陈敏任务收口)

### 11.1 签名鉴权实现
在 `XdrOpenApiAdapter` 中实现了符合深信服标准的 HMAC-SHA256 签名算法，支持通过 `XDR_AUTH_CODE` 进行联动。

### 11.2 字段映射与结构对齐
针对 8 月 29 日确认的真实响应结构，完成了以下精准对齐：
- **列表提取**：适配 `data.item` (单数) 结构的告警列表提取。
- **唯一标识**：使用 `uuId` 字段进行映射与去重。
- **时间处理**：支持 `lastTime` Unix 时间戳转换。
- **资产规则**：`hostIp` 优先映射到 `destination_ip`，`dstIp` 作为备选。

### 11.3 联调配置参考
```dotenv
PLATFORM_BACKEND=xdr_openapi
XDR_AUTH_TYPE=auth_code
XDR_AUTH_CODE=<受控注入>
XDR_ALERTS_PATH=/api/xdr/v1/alerts/list
XDR_ALLOW_FIXED_SAMPLE_FALLBACK=false
```

## 12. 变更记录

| 日期 | PR/Commit | 实现变化 | 相关测试 |
|---|---|---|---|
| 2026-08-25 | PR #17 / `1a5bbf1` | 新增告警关联专项回归与固定 JSONL 主链验证。 | `tests/test_alert_correlation_regression.py` |
| 2026-08-26 | PR #17 联调 | 在最新 `main@95defad` 上复验 JSONL 接入、关联和主链调用。 | 专项 17 项、全量 79 项通过。 |
| 2026-08-28 | PR #28 | 真实字段映射与 HMAC 签名逻辑实现。 | `test_xdr_real_contract.py` |
| 2026-08-29 | 联调收口 | **真实 XDR 只读调用成功 (8 条记录)**；同步 item/uuId/lastTime 等字段变更。 | 实机联调通过 |
