# 真实 XDR 输入契约与适配准备

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 任务编号 | `T0827-06` |
| 模块 | 平台工具（`platform-tools`） |
| 文档目的 | 为下一轮真实 XDR 只读接入准备**输入契约、字段映射和验收口径**，不实现或声称已经实现真实 XDR OpenAPI 调用。 |
| 适用基线 | `main@4190550`（已合并 PR #17 的后端主分支） |
| 关联代码 | `src/sec_agent/domain/models.py`、`src/sec_agent/platforms/base.py`、`src/sec_agent/platforms/jsonl_sample.py`、`src/sec_agent/platforms/raw_jsonl.py`、`src/sec_agent/services/ingest.py`、`src/sec_agent/bootstrap/container.py` |
| 敏感信息规则 | 真实 IP、事件/告警/资产 ID、用户名、URL、Token、Cookie、接入码、原始响应和响应截图均不得进入 Git、群聊、测试夹具或本文档。 |

> 本文档中的 `XDR` 字段名分为两类：**已由现有历史告警结构和固定样例确认的结构字段**，以及**必须在接入当天以 XDR OpenAPI/MCP 实际 Schema 确认的候选字段**。候选字段不是对厂商接口的断言，更不是可直接调用的请求参数。

## 2. 目标与非目标

本任务的目标是将真实 XDR 返回记录经适配层转换为当前主链可消费的 `AlertRecord`；如需保留标准化中间层，则先转换为 `NormalizedAlertRecord`。真实接入只替换输入来源，不能改变已经通过的固定 JSONL 回归路径、严重性专项规则或告警关联逻辑。

本任务不包含 XDR 地址、具体 HTTP 方法、端点路径、认证头名称、签名算法、分页字段名和真实响应字段名的猜测。这些内容必须以平台当天提供的 OpenAPI/MCP 工具 schema 为准，并仅在本地 `.env`、`*.local.json` 或受控运行环境保存。

## 3. 适配边界与数据流

```text
真实 XDR 只读查询
  → XDR response envelope（仅运行时内存）
  → XDR adapter（待实现：src/sec_agent/platforms/xdr_openapi.py）
  → NormalizedAlertRecord（可选中间契约）
  → AlertRecord（现有主链契约）
  → AlertIngestService / correlation / triage
```

当前 `PlatformAdapter.fetch_alerts(sample_id, xdr_event_id)` 已定义统一读取边界；但 `AlertIngestService` 对 `source="xdr"` 仍明确拒绝执行，容器层也未注册 `xdr_openapi` 后端。因此本轮只交付可审查的契约材料，**不能写成“真实 XDR 已接入”**。

## 4. 最小字段映射

| 外部 XDR 字段角色 | 已确认结构字段或接入日候选字段 | `NormalizedAlertRecord` 目标 | `AlertRecord` 目标 | 必填级别 | 转换与缺失规则 |
|---|---|---|---|---|---|
| 稳定唯一标识 | 候选：`event_id`、`alert_id`、`id` | `event_id` | `alert_id` | 必填 | 选择稳定、可跨分页去重的提供方标识；不得使用列表序号。若无稳定标识，拒绝该记录并留存脱敏错误原因。 |
| 发生时间 | 已确认结构：`alert_time`；候选：`event_time`、`occurred_at` | `event_time` | `occurred_at` | 必填 | 仅接受含时区的 ISO 8601 时间；无时区时必须按平台确认时区补齐并在 `scenario_fields` 留痕；无法解析则拒绝记录。 |
| 告警名称 | 已确认结构：`alert_name` | `rule_or_event_name` | `name` | 必填 | 去除首尾空白；空值拒绝记录。 |
| 事件分类 | 已确认结构：`alert_classification`；候选：`event_type` | `event_type` | `alert_type` | 条件必填 | 优先使用平台分类，经受控词典映射为 `sql_injection`、`webshell`、`lateral_movement`、`unauthorized_access` 或 `other`；未知值映射 `other` 并保留原值。 |
| 原始严重性 | 已确认结构：`alert_grade` | `severity` | `raw_severity` | 必填 | 通用映射：`严重→critical`、`高危→high`、`中危→medium`、`低危→low`；固定 WebShell 专项规则仅在名称为 `WebShell蚁剑工具文件管理` 且原始等级为 `高危` 时输出 `critical/95`。 |
| 源地址 | 已确认结构：`source_ip` | `source_ip` | `src_ip` | 可选 | 缺失保持 `None`；不以空字符串或 `0.0.0.0` 填充。 |
| 源端口 | 已确认结构：`source_port` | `source_port` | `src_port` | 可选 | 仅接受 `0..65535` 整数；无法转换则拒绝该字段值并记录缺失原因。 |
| 目的地址 | 已确认结构：`destination_ip`；回退：`host_ip` | `destination_ip`、`affected_asset` | `dst_ip`、`assets` | 条件必填 | 优先 `destination_ip`；仅在其缺失时回退 `host_ip`。若两者均无，事件仍可进入研判，但必须标注资产缺口，不得虚构资产。 |
| 目的端口 | 候选：`destination_port` | `destination_port` | `dst_port` | 可选 | 同源端口规则。 |
| 资产标识/名称 | 候选：`asset_id`、`asset_name`、`host_name` | `affected_asset` 或扩展字段 | `assets`、`scenario_fields` | 可选 | 地址优先作为 `assets` 主值；资产 ID/名称仅保留到受控 `scenario_fields`，展示与日志中需脱敏。 |
| 来源设备 | 已确认结构：`source_device_name`、`data_source` | `source_device_name` | `scenario_fields.source_device_name` | 必填 | 优先 `source_device_name`，再回退 `data_source`，最终回退常量 `XDR`；不得错误使用 STA 的 `reporting_device_name`。 |
| 攻击状态 | 候选：`attack_status`、`attack_result` | 扩展字段 | `attack_status` | 可选 | 原值保留并使用词典标准化；未知状态不影响读取。 |
| 证据引用 | 候选：原始告警 ID、日志 ID、证据 ID、详情链接 | `evidence_refs` | `evidence_refs` | 必填 | 生成不含凭据的内部引用，如 `xdr:<redacted-record-id>:<field-role>`；原始响应只以本地受控 `raw_record_ref` 指向。 |
| 数据来源 | 已确认结构：`data_source` | `evidence_source` | `source`、`scenario_fields` | 必填 | 标准来源为 `xdr`；保留提供方来源名称仅作审计上下文。 |

完整字段映射表见 [xdr_field_mapping.csv](xdr_field_mapping.csv)。

## 5. 必填、可选和拒绝规则

一个记录只有在取得稳定唯一标识、可解析发生时间、非空告警名称、可映射严重性、来源设备和最少一个可审计证据引用时，才可转换为 `AlertRecord`。事件类型可以由名称词典推断为 `other`；源/目的地址、端口和资产扩展信息可以缺失，但缺失必须显式记录为证据缺口，不能捏造默认地址或资产。

若同一记录同时携带 `destination_ip` 与 `host_ip`，适配器必须使用 `destination_ip` 作为 `affected_asset` 与 `dst_ip`；`host_ip` 可保留在受控扩展字段用于审计，但不得覆盖目的地址。WebShell 专项规则仅限已确定的固定场景名称和原始等级，不得将所有 XDR 高危告警一律升级为 `critical`。

## 6. 请求、响应与分页契约

本仓库不保存真实 XDR OpenAPI 请求或响应。可审查的无真实值结构位于：

- [xdr_list_alerts_request_sanitized.json](../../../tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json)
- [xdr_list_alerts_response_sanitized.json](../../../tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json)

请求层必须使用固定、含时区的时间窗口，并选择一种提供方分页方式：页码分页或游标分页，不能混用。`page_size` 必须不超过接入日 OpenAPI/schema 公布的上限；本文档不猜测该上限。分页过程中应按稳定 XDR 标识跨页去重；到达 `has_next=false`、空游标或总数上限后停止。读取型查询可以在网络超时时重试，但必须携带相同的查询窗口和幂等审计信息。

## 7. 错误、空结果与去重规则

| 场景 | 适配层处理 | 对主链的影响 |
|---|---|---|
| 认证/授权失败 | 分类为 `auth`，不重试；日志仅记录脱敏错误类别。 | 不生成虚假告警；由人工修正本地凭据。 |
| 网络连接/超时 | 分类为 `timeout`；仅对只读请求按有限次数重试。 | 本批次标记不完整，不能写成“无告警”。 |
| 平台返回非成功/结构无法解析 | 分类为 `platform_error` 或 `validation`。 | 拒绝该页或该记录，保留受控本地引用。 |
| 请求成功但列表为空 | 记录为 `success + zero_records`，不是连接失败。 | 不生成事件；必须与“查询实体不匹配”及“无数据源”区分。 |
| 单条记录缺稳定 ID/时间/名称/严重性 | 拒绝该记录并记录缺失字段名。 | 其余合格记录可继续；不得用列表下标补 ID。 |
| 跨页重复 | 使用提供方稳定 ID 去重；同一 ID 保留时间更完整、证据更多的一条，并记录去重数量。 | 防止重复告警被误判为多起安全事件。 |
| 固定样例查询真实 MCP/XDR | 固定 RFC 5737 IP 与占位 ID 不作为真实查询实体。 | 预期可能零命中，应走 `no_data/人工接管` 而非伪造证据。 |

## 8. 脱敏与运行时实体桥接

仓库中的样例只能表达结构与规则，不能承载真实平台实体。接入运行时从同一条真实 XDR 事件提取的 `event_id`、`alert_id`、`asset_id`、源/目的地址和时间范围，仅可存在于进程内存、受控本地密钥/配置或平台审计系统中。若需要在开发环境临时保存调试响应，文件必须使用 `*.local.json` 或其他已忽略路径，并在验证后删除。

对可提交样例采用以下处理：IP 替换为 RFC 5737 文档保留地址；ID 替换为语义化占位符；资产/主机/用户替换为泛化标签；时间使用占位格式或整体平移；证据引用只保留字段角色和匿名本地引用。所有时间关联、去重关系和严重性规则必须保持不变。

## 9. 明日接入前验收清单

1. 由平台负责人提供只读 OpenAPI/MCP 的真实 schema、认证方式、分页字段和允许的查询范围；不在 Git 或群聊粘贴密钥。
2. 用一条真实 XDR 事件在本地确认稳定唯一 ID、发生时间时区、严重性枚举、源/目的地址与资产字段的实际名称。
3. 对照本契约运行适配器，将真实输入转换为 `AlertRecord`，并验证 `raw_record_ref`、`evidence_refs`、分页去重和缺失字段处理。
4. 使用同一条真实事件的运行时实体查询 MCP/DBProxy；连接成功但零命中必须记录为 `no_data`，不能当成工具失败或有效证据。
5. 保持 `fixed_sample` 与 `jsonl_sample` 输入模式可用，执行已有固定样例回归，确认真实接入不会破坏离线降级路径。

## 10. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-08-27 | 首次建立 XDR 输入契约 | 本轮只准备映射和脱敏结构，不包含真实 XDR 请求、凭据、响应或适配器实现。 |
