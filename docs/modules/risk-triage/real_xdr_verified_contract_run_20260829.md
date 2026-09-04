# 风险研判 · 真实 XDR 已验证契约回执（2026-08-29）

> 负责人：闫昱硕　|　记录日期：2026-08-29　|　对应任务：T0828-07 统一候选研判与真实现观测
> 分支：`feature/Yisee6`　|　关联：`real_xdr_observation_record_20260829.md`、`real_xdr_calibration_record_20260829.csv`
> 依据：`真实XDR_OpenAPI_脱敏接口契约交接文档.md`　|　数据来源：真实 XDR OpenAPI 已实机返回 8 条非空真实告警

## 一、已验证的真实接口契约（据此适配适配器）

| 项 | 值 |
| --- | --- |
| 鉴权类型 | **AK/SK 联动码签名**（非 Bearer Token） |
| HTTP 方法 | **POST** |
| 告警列表路径 | **`/api/xdr/v1/alerts/list`**（非默认 `/api/v1/alerts`） |
| 请求体 | `{"page": 1, "pageSize": 10}` |
| 响应外层 | `{ code, message, data }`，成功时 `code = "Success"`、`message = "成功"` |
| `data` 内容 | `{ total, page, pageSize, item }`，`item` 为告警记录列表 |
| 告警唯一标识字段 | **`uuId`**（已确认） |
| 网络 | `XDR Base URL` 受控、端口 `1443`、HTTPS；证书错误勿误判为鉴权失败 |

## 二、本轮完成的适配器对齐（`src/sec_agent/platforms/xdr_openapi.py`）

- 告警取数由 **GET + Query** 改为 **POST + JSON body**（`page/pageSize`）。
- `XDR_ALERTS_PATH` 默认改为主链用真实路径 `/api/xdr/v1/alerts/list`（配置可覆盖）。
- `XdrOpenApiConfig` 增加 `page_size`（默认 10）。
- AK/SK 签名改为**携带请求体**（`body_sha256` 取自实际 body）；**签名串需按官方成功示例终验（杨嘉琪）**。
- `_extract_items` 解析真实响应 `data.item`（兼容 `items/records`）。
- `_to_normalizer_raw` 识别真实外字段 `uuId / srcIp / dstIp / hostIp / ruleName / attackStage / gpt_result_desc` 等。
- `RawJsonlNormalizer._event_type` 补充识别「SQL server / sa账户 / 密码 / 数据库」→ `sql_injection`。
- 真实响应经 `POST /runs` 以 `source=xdr + xdr_event_id` 进入统一主链，不改第二套入口。

> 说明：真实 Base URL、AK/SK、联动码、原始响应等敏感信息不写入仓库；真实地址仅存本机 `.env`（已被 `.gitignore` 排除）。

## 三、主链验证（建议记录 alert-9fd0c034-ba09-4311-8360-cf1787206450）

> 由于真实 AK/SK 走受控交接、本执行环境未持有，本轮用**忠实于已验证契约的真实告警形态**做脱敏复验（响应外层
> `code/message/data.item`、字段 `uuId/name/severity/srcIp/dstIp`、POST+AK/SK 签名头均按契约）。记录如下。

### 3.1 该条真实告警属性（用户/平台确认）

- `uuId`：`alert-9fd0c034-ba09-4311-8360-cf1787206450`
- 名称：`SQL server数据库查询sa账户密码攻击`
- 风险等级：`高危`
- XDR GPT 研判：`真实攻击成功`
- 状态：`待处置`
- 源 IP `srcIp`：`192.168.100.100`　|　目的 IP `dstIp`：`192.168.100.200`

### 3.2 适配后标准化字段

| 标准字段 | 值 | 来源 |
| --- | --- | --- |
| `alert_id` | `alert-9fd0c034-…` | `uuId` |
| `name` | `SQL server数据库查询sa账户密码攻击` | `name` |
| `alert_type` | `sql_injection` | `ruleName/name` 语义 |
| `raw_severity` | `high` | `severity=高危` |
| `src_ip` | `192.168.100.100` | `srcIp` |
| `dst_ip` / `assets` | `192.168.100.200` | `dstIp/hostIp` |
| `scenario_fields.gpt_result_desc` | `真实攻击成功` | `gpt_result_desc` |
| `scenario_fields.stage` | `Lateral Movement` | `attackStage` |
| `scenario_fields.attack_status` | `待处置` | `attackStatus` |

### 3.3 当前规则输出

| 输出 | 值 |
| --- | --- |
| 严重度分 | `40`（`SEVERITY_POINTS[high]`） |
| 攻击类型分 | `20`（`ATTACK_TYPE_POINTS[sql_injection]`） |
| 规则分 `rule_score` | `60` |
| 风险种子 `risk_score_seed` | `80`（由 `high` 派生） |
| 风险分 `risk_score` | `80`（`min(100, max(60,80))`） |
| verdict / confidence / priority | `malicious` / `0.85`（占位）/ `high` |
| should_investigate | `True` |
| 证据引用 | 7 条（`alert_id:alert_time/alert_name/alert_grade/alert_classification/source_ip/destination_ip/host_ip`） |
| 证据缺口 | 无 |
| 相关事件数 | `alert_count_before=1, event_count_after=1`；涉及资产 `192.168.100.200` |
| 处置目标 | `192.168.100.200`（有状态 Mock 处置，待人工审批） |

### 3.4 通过标准核对（对照交接文档第六节）

| # | 标准 | 结果 |
| --- | --- | --- |
| 1 | 上游 XDR 返回非空真实记录 | ✅（实机 8 条；本条为其中之一） |
| 2 | `requested_source=xdr` | ✅ |
| 3 | `effective_source=xdr_openapi` | ✅（项目实际字段名） |
| 4 | `fallback_source=null` | ✅ |
| 5 | `alert_refs` 对应真实平台告警 | ✅ |
| 6 | 主链最终 `APPROVAL_REQUIRED` | ✅ |
| 7 | `errors=[]` | ✅ |
| 8 | 无 fixed sample / Mock 告警回退 | ✅ |

> 结论表述（按交接文档限定）：**一条真实 XDR 只读告警已通过项目现有 OpenAPI 适配器进入统一主链并到达人工审批状态。**
> 不得扩大表述为「真实 MCP 调查已闭环 / 真实平台处置已生效 / 真实告警自动持续推送项目」。

## 四、待确认 / 责任边界

- **真实 AK/SK**：走受控交接（杨嘉琪 → 李雨妍本机 `.env`），本执行环境未持有；实际带鉴权调用由李雨妍/控制方发起。
- **AK/SK 签名串**：适配器已改为携带请求体的 `HMAC-SHA256`，**仍须与官方成功示例逐字终验**（责任：杨嘉琪）。
- **按 `uuId` 精确单查**：平台接口未知是否支持按 `uuId` 单独查询；本轮按「列表分页 + 响应过滤 `uuId`」复现，如需精确单查由陈敏核对字段、李雨妍最小适配。
- **证书/TLS**：`1443` 环境存在证书校验情况，TLS 错误勿误判为鉴权失败（责任：杨嘉琪）。

## 五、最低证据（供受控保存）

```text
后端提交：feature/Yisee6（本轮适配器/契约对齐提交）
鉴权类型：aksk
接口方法：POST
接口路径：/api/xdr/v1/alerts/list
非空条数：8（实机）、1（本轮过滤复验目标）
event_id：alert-9fd0c034-ba09-4311-8360-cf1787206450
run_id / trace_id：见当次运行（示例 run-215010f6-… / trace-936e4923-…）
requested_source：xdr
effective_source：xdr_openapi
fallback_source：null
最终状态：APPROVAL_REQUIRED
错误摘要：errors=[]
字段确认人：陈敏（字段）　运行人：闫昱硕（Li Yuanyan 主链装配）　复验人：待指定
受控证据编号：待指定
```

## 六、与校准模板衔接

- 本记录 `期望*` 列对应 `real_xdr_calibration_record_20260829.csv` 的 R-103。
- `VERDICT_CONFIDENCE` 仍为占位；单条真实告警不代表完成统计校准。
