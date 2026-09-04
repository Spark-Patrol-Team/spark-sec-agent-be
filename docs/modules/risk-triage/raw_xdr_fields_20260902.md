# 昨天运行真实事件原始字段（2026-09-02）

> 事件：`evt-9b6df22d-bbb5-4d84-b340-a969099bcfc9`
> 运行：`run-776923de-7218-48aa-8c7a-a9fee2694a1f`
> 追踪：`trace-c9a22655-e6af-47c4-83e5-9402842a559b`
> 说明：后端为 `memory` 存储，重启后事件已消失；本清单由运行时的证据引用、事件实体与同 `uuId` 原始样例还原。
> 命名约定（2026-09-04 陈敏确认）：`evidence_refs[].ref_id` 使用 XDR API **原始字段名**（无 `xdr_` 前缀，如 `…:gptResultDescription`）；`scenario_fields` 使用 `xdr_*` 前缀（如 `xdr_gptResultDescription`）。`attackState`（攻击状态 0/2）与 `stage`/`xdr_stage`（阶段数值，如 30）是不同字段，旧记录中的 `attackStage` 应更正为 `stage`/`xdr_stage`。

## 原始字段

| 原始字段                   | 值                                            | 来源                         |
| ---------------------- | -------------------------------------------- | -------------------------- |
| `uuId`                 | `alert-9fd0c034-ba09-4311-8360-cf1787206450` | 运行抓取 / 样例                  |
| `name`                 | `SQL server数据库查询sa账户密码攻击`                    | 同 uuId 样例                  |
| `severity`             | `70`（数值，映射为高危）                               | 样例                         |
| `lastTime`             | 事件时间 `2026-08-21T13:43:23+08:00`             | 运行抓取（样例 `1787155200` 为脱敏值） |
| `srcIp`                | `["192.168.100.100"]`                        | 运行抓取 + 样例                  |
| `hostIp`               | `"192.168.100.200"`                          | 运行抓取 + 样例                  |
| `dstIp`                | `"192.168.100.200"`                          | 运行抓取（事件 `dst_ips`）         |
| `devSourceName`        | `STA (STA_001-04AABE1B)`                     | 运行抓取（事件实体）                 |
| `gptResultDescription` | `真实攻击成功`                                     | 样例                         |
| `confidence`           | `20`                                         | 样例                         |
| `attackState`          | 原始值未暴露                                       | 运行抓取（证据引用含该字段）             |
| `alertDealAction`      | 原始值未暴露                                       | 运行抓取（证据引用含该字段）             |
| `traceBackId`          | 数组，含 21 条 `network_security_log-*`           | 运行抓取（证据引用）                 |

# 
