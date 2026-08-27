# 平台工具模块开发说明

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 模块名称 | 平台工具（`platform-tools`） |
| 本轮任务 | `T0827-06`：真实 XDR 输入契约与适配准备 |
| 负责人 | 陈敏 |
| 适用基线 | `main@4190550` |
| 本轮状态 | 已完成契约、字段映射、脱敏结构样例和最小契约测试；未实现真实 XDR HTTP/OpenAPI/MCP 读取。 |

## 2. 当前代码结构与真实状态

| 位置 | 当前职责 | 与真实 XDR 接入的关系 |
|---|---|---|
| `src/sec_agent/domain/models.py` | 定义 `NormalizedAlertRecord`、`AlertRecord`、`ToolRequest`、`ToolResult` 等主链契约。 | 真实适配器必须遵循，不应修改字段语义。 |
| `src/sec_agent/platforms/base.py` | 定义 `PlatformAdapter.fetch_alerts(sample_id, xdr_event_id)` 协议。 | 真实 XDR 适配器应实现该协议。 |
| `src/sec_agent/platforms/jsonl_sample.py` | 将固定 JSONL 转换为 `AlertRecord`。 | 当前可复用的输出形状和证据引用口径。 |
| `src/sec_agent/platforms/raw_jsonl.py` | 将脱敏 raw JSONL 标准化为 `NormalizedAlertRecord`。 | 当前已验证的字段规则参考，不是 XDR OpenAPI 客户端。 |
| `src/sec_agent/services/ingest.py` | 向 `PlatformAdapter` 委派读取。 | 目前对 `source="xdr"` 明确抛出未实现错误。 |
| `src/sec_agent/bootstrap/container.py` | 装配 `fixed_sample` 与 `jsonl_sample`。 | 目前未注册 `xdr_openapi` 后端。 |
| `src/sec_agent/tools/xdr_query_tool.py` | 内置 XDR 查询演示工具。 | 返回的是内置 mock 记录，不能作为真实 XDR 接入证据。 |

真实接入应新增独立适配器文件，例如 `src/sec_agent/platforms/xdr_openapi.py`。该适配器只负责请求构造、响应解析、分页去重、字段标准化、结构化错误和证据引用；业务 service、关联、风险研判和处置层不得直接拼接厂商 HTTP 路径或读取认证信息。

## 3. 本轮交付文件

| 文件 | 用途 |
|---|---|
| `docs/modules/platform-tools/xdr_input_contract.md` | 真实 XDR 输入最小字段映射、分页、去重、错误和脱敏规则。 |
| `docs/modules/platform-tools/xdr_field_mapping.csv` | 可审查的字段级映射表。 |
| `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | 无真实值的请求结构样例。 |
| `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | 无真实值的响应结构样例。 |
| `tests/test_xdr_input_contract.py` | 验证契约样例、资产/设备规则和脱敏限制的最小测试。 |

## 4. 运行配置与敏感信息规则

现有 `.env.example` 中保留 `XDR_BASE_URL`、`XDR_AUTH_TYPE`、`XDR_TOKEN`、`XDR_CONNECT_TIMEOUT_SECONDS`、`XDR_READ_TIMEOUT_SECONDS` 等**占位配置**。在真实接入前，必须先以平台实际文档确认字段名称、认证方式、端点路径、TLS 要求、分页模型和速率限制；不能根据这些占位变量猜测 API 协议。

真实 URL、Token、Cookie、接入码、用户名、客户端证书、真实 IP、真实事件 ID、告警 ID 和原始响应只能写入本地 `.env`、密钥管理服务或已忽略的 `*.local.json`。不得写入 `.env.example`、Markdown、CSV、JSON fixture、测试断言、日志 preview、提交信息、PR 描述或群聊。

建议接入当天使用如下本地配置原则，而非提交具体值：

```text
PLATFORM_BACKEND=xdr_openapi
XDR_BASE_URL=<local_only>
XDR_AUTH_TYPE=<provider_defined>
XDR_TOKEN=<local_only_secret>
XDR_CONNECT_TIMEOUT_SECONDS=<provider_and_network_confirmed>
XDR_READ_TIMEOUT_SECONDS=<provider_and_network_confirmed>
```

## 5. 真实适配器实现步骤

1. 从 XDR OpenAPI/MCP schema 获取实际只读查询参数与响应字段，记录字段名称和枚举，不记录真实值或凭据。
2. 以固定含时区时间窗口构造请求；按平台实际规则选择页码或游标分页，禁止混用。
3. 将单条提供方记录转换为 `NormalizedAlertRecord`（可选）和 `AlertRecord`；稳定 ID、发生时间、名称、严重性、来源设备和证据引用不足时拒绝该条记录。
4. 对 `destination_ip` 与 `host_ip` 强制执行目的地址优先规则；用稳定提供方 ID 做跨页去重。
5. 将 `raw_record_ref` 指向受控本地审计引用；`evidence_refs` 仅存匿名内部引用，不携带 URL、Token 或原始响应。
6. 对认证、超时、平台错误、解析错误、零记录和单条记录拒绝分别分类；零记录不是传输失败，也不能生成虚假告警。
7. 在容器层显式注册 `PLATFORM_BACKEND=xdr_openapi`，保留 `fixed_sample` 与 `jsonl_sample` 的现有入口。
8. 使用一条真实 XDR 事件在本地受控环境验证后，复跑固定 JSONL 回归，确认真实接入没有破坏已通过的关联逻辑。

## 6. 调试与验证命令

本轮可直接运行的脱敏结构测试：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_xdr_input_contract.py'
```

现有固定 JSONL 回归命令：

```bash
PYTHONPATH=src python -m unittest tests.test_jsonl_platform tests.test_raw_jsonl_ingest_and_correlation tests.test_alert_correlation_regression
```

真实 XDR 适配器尚未实现，以下命令仅为接入后应执行的形式，不代表当前可用：

```bash
PLATFORM_BACKEND=xdr_openapi PYTHONPATH=src python -m sec_agent.scripts.run_flow
```

## 7. 错误处理与安全限制

| 类型 | 适配器行为 | 禁止行为 |
|---|---|---|
| `auth` | 停止请求，记录脱敏错误类别，人工修正本地凭据。 | 重复暴力重试、输出认证头或 Token。 |
| `timeout` | 仅对只读请求有限重试，保持相同时间窗口和请求语义。 | 更改筛选条件后将不同查询混为一次结果。 |
| `platform_error` | 保留匿名审计引用并停止该页/批次。 | 将平台错误解释为“无告警”。 |
| `validation` | 拒绝缺稳定 ID、时间、名称或严重性的记录。 | 用页号、空值或硬编码常量伪造字段。 |
| `zero_records` | 记录为成功但零命中。 | 将零命中视为连接失败或虚构告警证据。 |

## 8. 与杨嘉琪的接口边界

陈敏负责确认上游事件映射、固定样例与真实实体的隔离规则、`AlertRecord` 所需字段和验收口径。杨嘉琪负责确认深信服 XDR OpenAPI/MCP 的真实只读入口、schema、认证、权限、分页和真实工具调用结果。真实接入实现前，双方必须用同一条真实 XDR 事件在本地比对字段存在性，但不把该事件原值带入 Git。

## 9. 已知限制与变更记录

当前没有启用的 XDR 连接器，仓库也没有 `xdr_openapi.py` 和真实后端装配，因此本轮没有、也不声称已经完成真实平台读取。固定样例只用于离线回归；`platform_derived` 表示字段结构源于已验证平台记录并完成脱敏，`synthetic_regression` 表示合成回归数据。

| 日期 | 变更 |
|---|---|
| 2026-08-27 | 补充 T0827-06 的真实 XDR 输入契约交付、实现位置、配置边界、调试命令和接入分工。 |
