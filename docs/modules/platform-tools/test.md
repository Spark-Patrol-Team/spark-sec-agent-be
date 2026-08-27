# 平台工具模块测试说明

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 模块名称 | 平台工具（`platform-tools`） |
| 本轮任务 | `T0827-06`：真实 XDR 输入契约与适配准备 |
| 负责人 | 陈敏 |
| 适用基线 | `main@4190550` |
| 测试范围 | 脱敏请求/响应结构、XDR 最小字段契约、目的资产和来源设备规则、零记录语义、现有固定样例回归不受影响。 |
| 非测试范围 | 未使用真实 XDR 地址、真实凭据、真实事件、真实告警、真实资产或原始响应；未执行真实 OpenAPI 请求。 |

## 2. 测试策略

本轮测试采用“结构契约 + 既有回归”方式。结构契约确保真实接入前的请求/响应样例可解析，具有明确时间窗口、分页、稳定标识、资产/设备和错误语义，同时不携带真实平台实体。既有回归确保新增文档和契约夹具不改变 `fixed_sample`、`jsonl_sample`、raw JSONL 标准化与告警关联的既有行为。

真实 XDR 连接、认证、分页和业务命中验证必须在下一轮由平台负责人提供只读接口资料后，在本地受控环境完成。真实实体不得进入本文件、测试代码、提交日志或 CI 输出。

## 3. 测试对象

| 对象 | 路径 | 目的 |
|---|---|---|
| 请求结构样例 | `tests/fixtures/xdr_contract/xdr_list_alerts_request_sanitized.json` | 验证时间窗口、筛选、分页和本地认证边界。 |
| 响应结构样例 | `tests/fixtures/xdr_contract/xdr_list_alerts_response_sanitized.json` | 验证最小记录字段、资产/设备优先级、零结果语义和脱敏占位符。 |
| 契约测试 | `tests/test_xdr_input_contract.py` | 机器验证两个 JSON 文件的可解析性和关键规则。 |
| 既有告警回归 | `tests/test_jsonl_platform.py`、`tests/test_raw_jsonl_ingest_and_correlation.py`、`tests/test_alert_correlation_regression.py` | 确保固定 JSONL 标准化、关联与研判主链不被本轮材料影响。 |

## 4. 用例与结果

| 用例 ID | 目的 | 输入/前置 | 预期结果 | 本轮结果 |
|---|---|---|---|---|
| PT-XDR-01 | 请求结构可解析 | 脱敏请求 JSON | 存在 `time_range`、筛选、提供方定义的分页和本地认证边界。 | Pass |
| PT-XDR-02 | 响应最小字段完整 | 脱敏响应 JSON | 单条记录包含标识、时间、名称、等级、源/目的地址、数据源和证据标识字段。 | Pass |
| PT-XDR-03 | 无真实实体泄露 | 两份脱敏 JSON | 标识为占位符；无 URL、Bearer Token、真实 API 地址；RFC 5737 地址仅作样例。 | Pass |
| PT-XDR-04 | 目的资产规则 | 响应结构 `destination_ip` 与 `host_ip` | 规则固定为 `destination_ip` 优先、`host_ip` 缺失回退。 | Pass |
| PT-XDR-05 | 来源设备规则 | 响应结构 | `source_device_name` 优先，`data_source` 回退，最终为 `XDR`。 | Pass |
| PT-XDR-06 | 空结果语义 | `records=[]` 的真实接入语义 | 应记录为请求成功但零记录，不等同于认证或连接失败。 | Pass（契约规则已固化） |
| PT-XDR-07 | 固定 JSONL 不回归 | 已合并的固定样例 | SQLi `high/80`、WebShell `critical/95`、横向移动 `medium/65` 规则不变。 | 待真实适配器实施后复跑；本轮未改现有代码。 |
| PT-XDR-08 | 真实 XDR 最小验证 | 本地受控真实事件 | 确认 schema、认证、分页、字段、去重和一条记录转换；只输出脱敏结论。 | 待明日接口资料与只读权限明确。 |

## 5. 本轮实际执行命令与结果

本轮已实际执行以下契约测试命令：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_xdr_input_contract.py'
```

实际执行结果：4 项通过（`Ran 4 tests`，`OK`）。覆盖请求的运行时传输与分页边界、响应最小字段、资产/空结果规则和“样例地址不是真实查询实体”声明。该测试不访问网络、平台或 MCP。

本轮还实际执行了以下固定样例回归命令；它们不依赖真实 XDR：

```bash
PYTHONPATH=src python -m unittest tests.test_jsonl_platform tests.test_raw_jsonl_ingest_and_correlation tests.test_alert_correlation_regression
```

实际执行结果：17 项通过（`Ran 17 tests`，`OK`）。该结果确认新增契约文件没有改变 SQLi `high/80`、WebShell `critical/95`、目的地址优先、raw JSONL 读取、15 分钟关联、证据引用和自动进入研判的既有回归行为。

## 6. 接入日验收步骤

1. 平台负责人在本地受控环境配置真实 XDR 只读入口与凭据，不提交配置文件。
2. 以同一条真实 XDR 事件记录字段存在性：稳定 ID、时间及时区、名称、等级、源/目的地址、资产、设备来源、证据标识和分页标记。
3. 使用固定时间窗口查询第一页和下一页，检查跨页稳定 ID 去重；不在终端、截图或文档输出真实记录。
4. 对照 [xdr_field_mapping.csv](xdr_field_mapping.csv) 验证适配器输出的 `AlertRecord` 字段，重点检查目的地址优先和来源设备映射。
5. 验证零命中、认证失败、网络超时、解析失败和单记录缺字段的区别；不得将平台错误写为“无告警”。
6. 复跑 PT-XDR-07 的固定 JSONL 回归，确认新适配器不破坏离线降级路径。

## 7. 结果解释与限制

边界与异常用例通过，表示系统拒绝不完整、歧义或超出规则的输入，属于预期安全行为，不是缺陷。`PT-XDR-06` 仅验证了当前文档契约；真实 MCP/XDR “连接成功但业务零命中”的分类处理仍需由真实工具实现和测试覆盖，不能因为结构样例通过而声称真实工具已经可用。

本轮没有真实 XDR 读接口、认证信息、端点 schema 或运行时实体，也没有在真实环境执行写操作。因此当前测试不能证明真实 XDR 可拉取数据，只证明接入所需的仓库内契约、脱敏边界和回归保护已准备完毕。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-27 | 补充 T0827-06 的 XDR 契约测试对象、用例、接入日验证步骤和真实接入限制。 |
