# XDR 真实字段映射核对表 (T0828-06)

**日期**：2026-08-29  
**负责人**：陈敏  
**基线方案**：《2026年8月29日真实XDR告警输入接入解决方案》

## 1. 映射核对结论

经过核对杨嘉琪提供的最新 8 条真实告警样本（含 SQL 注入、WebShell、文件上传等场景），当前 `XdrOpenApiAdapter._to_normalizer_raw()` 的逻辑与真实响应结构**完全匹配**。

- **核心标识**：`uuId` 成功映射为 `sample_id`。建议首选验证 ID：`alert-9fd0c034-ba09-4311-8360-cf1787206450`。
- **时间维度**：`lastTime` (Unix) 成功转换为系统标准 UTC 时间。
- **资产定位**：`hostIp` 优先作为目的资产，`dstIp[0]` 作为备选，符合业务预期。
- **严重度**：`severity >= 70` 映射为“高危”，其余为“中危”，符合研判基准。
- **扩展字段**：`gptResultDescription`、`confidence` 等已通过 `scenario_fields` 完整保留。

**结论：无需修改核心代码，现有适配器已具备接入真实数据的能力。**

## 2. 响应结构对齐 (8/29 关键发现)

真实响应的 `data` 节点下，告警列表字段名为 **`item`** (单数)，而非通用的 `items`。系统适配器已完成对此特殊命名的兼容处理。

## 3. 详细字段对照表

| 真实 XDR 字段 (原始) | 系统内部字段 (NormalizedAlertRecord) | 转换/处理逻辑 | 验证状态 |
| :--- | :--- | :--- | :--- |
| `uuId` | `event_id` | 直接映射 | ✅ 已验证 |
| `name` | `alert_name` | 直接映射 | ✅ 已验证 |
| `lastTime` | `event_time` | Unix 时间戳 -> datetime (UTC) | ✅ 已验证 |
| `severity` | `severity` | `>= 70` -> 高危; `< 70` -> 中危 | ✅ 已验证 |
| `hostIp` | `destination_ip` | 字符串提取 | ✅ 已验证 |
| `srcIp` | `source_ip` | 取数组首项 `srcIp[0]` | ✅ 已验证 |
| `dstIp` | `destination_ip` | 若 `hostIp` 缺失，取 `dstIp[0]` | ✅ 已验证 |
| `devSourceName` | `source_device_name` | 取数组首项 `devSourceName[0]` | ✅ 已验证 |
| `traceBackId` | `evidence_refs` | 数组保留，用于证据追溯 | ✅ 已验证 |
| `gptResultDescription` | `scenario_fields.gpt_result_desc` | 存入扩展字段 | ✅ 已验证 |
| `confidence` | `scenario_fields.confidence` | 存入扩展字段 | ✅ 已验证 |

## 4. 脱敏转换结果示例 (1/8)

**输入 (脱敏原始 XDR):**
```json
{
  "uuId": "alert-9fd0c034-ba09-4311-8360-cf1787206450",
  "name": "SQL server数据库查询sa账户密码攻击",
  "severity": 70,
  "gptResultDescription": "真实攻击成功",
  "srcIp": ["192.168.100.100"],
  "hostIp": "192.168.100.200",
  "lastTime": 1787155200
}
```

**输出 (系统 AlertRecord):**
```json
{
  "alert_id": "alert-9fd0c034-ba09-4311-8360-cf1787206450",
  "name": "SQL server数据库查询sa账户密码攻击",
  "occurred_at": "2026-08-15T16:00:00Z",
  "raw_severity": "high",
  "assets": ["192.168.100.200"],
  "source_device_name": "XDR",
  "scenario_fields": {
    "gpt_result_desc": "真实攻击成功",
    "confidence": 20,
    "attack_stage": 30
  }
}
```

## 5. 运行建议
1. 联调时请务必关闭 fallback：`XDR_ALLOW_FIXED_SAMPLE_FALLBACK=false`。
2. 确保环境已配置 `XDR_AUTH_CODE`。
