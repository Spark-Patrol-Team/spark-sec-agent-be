# 事件字段—来源—信号强度合同（v1.1）

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 合同名称 | 事件字段—来源—信号强度合同 |
| 版本号 | **v1.1**（登记方与冻结方共用同一个版本号） |
| 登记（信号语义） | 陈敏，告警关联模块，2026-09-13 |
| 冻结（代码接口确认） | 杨嘉琪，门禁与主链接口 —— D1 已按 Review 实现（`38cee87`）；D2/D3/D4 待确认 |
| 适用代码基线 | `main@0001bbd`（PR #50 已合入 main；本合同自 v1.1 起以 main 为基线） |
| 门禁实现 | `src/sec_agent/services/gatekeeper.py` |
| 字段生产 | `src/sec_agent/services/correlation.py`、`src/sec_agent/services/triage.py` |
| 桥接 | `src/sec_agent/services/deep_agent_bridge.py::_to_deep_agent_input` |
| 代码一致性测试 | `tests/test_event_field_signal_contract.py` |
| 门禁边界测试 | `tests/test_gatekeeper_boundary.py` |

本合同不是第二套设计文档：它只回答“主链到底如何理解这些字段”。字段来源、信号的语义由登记方负责；
接口是否真的按该语义实现由冻结方确认。任何一方改动字段来源或判定语义，必须同时升版本号并重跑上述两份测试，
不允许只改代码或只改文档。

## 1. 字段来源

链路是**三段**，字段在每一段都可能被裁剪或改名，下面所有结论都以“门禁实际能看到什么”为准：

```text
SecurityEvent（12 字段，含 summary / alert_refs / alert_summaries / evidence_summaries）
  → DeepAgentBridge._to_deep_agent_input() 只映射 13 字段
  → SecurityEventInput（13 字段）
  → WebShellGatekeeper 只读其中白名单 10 字段
```

因此 `summary`、`alert_refs`、`alert_summaries`、`evidence_summaries` **都不是 `SecurityEventInput` 的字段**，
门禁读不到它们本身；其中引用类字段由 bridge 先序列化成字符串，再随 `alerts` / `evidence` 进入白名单。

| 字段 | 产生位置 | 语义 | 是否进入 `SecurityEventInput` | 门禁是否可读 | 为空 / 缺失时 |
|---|---|---|---|---|---|
| `event_id` | `AlertCorrelationService.correlate` | 事件标识 | 是（`event_id`） | 可读，仅用于输入质量检查 | 记录“必填字段为空或非法” |
| `event_type` | `correlate()` 取同一事件内已校验一致的 `alert_type`（`correlation.py:71`） | **机器事件类型 token**（`webshell` / `sql_injection` / `lateral_movement` / `unauthorized_access` / `other`） | 是（`event_type`） | 可读，只作弱信号 | 不产生事件类型信号，按第 4 节降级 |
| `summary` | `correlate()` | 面向人的压缩摘要句 | **否**（bridge 不映射） | **不可读**（既不在 `SecurityEventInput`，也不在门禁白名单） | 不参与门禁判定；仅供人阅读 |
| `alert_refs` | `correlate()`，取 `AlertRecord.alert_id`（真实 XDR `uuId`） | 审计定位锚点 | 否（bridge 序列化进 `alerts`） | 经 `alerts` 文本可读（只作文本载体，无独立语义） | 与 `alert_summaries` 同步缺失 |
| `alert_summaries` | `correlate()`，`{alert_id: alert.name}` 映射（`correlation.py`） | **以告警 ID 为键**的告警名称；与 `alert_refs` 键集合一致 | 否（bridge 序列化进 `alerts`） | 经 `alerts` 文本可读（文本信号） | 该条只保留 ID |
| `supporting_evidence_refs` | `RiskTriageService.triage`，按**入参告警顺序**展开 `evidence_refs.ref_id`（`triage.py:48`） | 证据定位锚点 | 否（bridge 序列化进 `evidence`） | 经 `evidence` 文本可读（只作文本载体，无独立语义） | 无证据时为空列表 |
| `evidence_summaries` | `correlate()`，`{ref_id: summary}` 映射，**过滤空摘要**（`correlation.py`） | **以证据 ref_id 为键**的摘要；与 `supporting_evidence_refs` 按 ID 对应 | 否（bridge 序列化进 `evidence`） | 经 `evidence` 文本可读（文本信号） | 该条只保留 ID |
| `triage.verdict` | 风险研判模块 | 结构化研判结论（`malicious` / `benign` / `uncertain`） | 是（`triage.verdict`） | 可读 | 不产生研判信号 |
| `initial_verdict` | 上游初步研判文本 | 初步结论文本 | 是（`initial_verdict`） | 可读 | 不产生研判信号 |
| `confidence` / `trace_id` / `run_id` | 上游 | 置信度与链路标识 | 是 | **禁止读取**（在输入里但不在白名单） | 与判定无关 |

`SecurityEventInput` 的 13 字段与门禁白名单 10 字段的对应关系（可机械校验，见 `tests/test_event_field_signal_contract.py`）：

```text
输入 13 字段：event_id, event_type, severity, timestamp, source_ip, target_ip,
              alerts, evidence, initial_verdict, confidence, triage, trace_id, run_id
白名单 10 字段：event_id, event_type, severity, timestamp, source_ip, target_ip,
              alerts, evidence, initial_verdict, triage
白名单 ⊆ 输入；输入 − 白名单 = {confidence, trace_id, run_id}；summary 不属于任何一侧
```

桥接（`deep_agent_bridge.py::_described_refs`）**按 ID 查映射**后拼成 `<ref_id>: <摘要>` 交给门禁与 Agent；
映射中查不到（或摘要为空）的引用只保留裸 ID。禁止把“全部 ID 列表”和“仅非空摘要列表”按数组下标拼接。
`summary` 既不进入 Agent 输入也不进入门禁，所以“不得用 `summary` 反推 `event_type`”是**bridge 之前的义务**，
门禁侧不存在读取 `summary` 的可能性。

## 2. 信号来源与强度

门禁只从白名单 10 个字段读取信号（`gatekeeper.py:43`），每条信号都标注来源：
`event_type` / `alerts` / `evidence` / `triage` / `initial_verdict`。

强度 6 级（`SignalStrength`）：`OUT_OF_SCOPE`、`BENIGN_LIKE`、`INDETERMINATE`、
`IN_SCOPE_WEAK`、`IN_SCOPE_CONFIRMED`、`MIXED`。

同一段文本按下列顺序判定，命中即停止（`gatekeeper.py:304`）：

1. 域外关键词（SSH/暴力破解/供应链/XSS/驱动内核等，`gatekeeper.py:137`）→ `OUT_OF_SCOPE`；
2. 合法语境关键词（已知业务 API、头像上传、部署尝试未成功等，`gatekeeper.py:126`）→ `BENIGN_LIKE`；
3. WebShell 专属强证据（`Process.Start`、`w3wp.exe`、`System.Runtime.InteropServices`、`反序列化攻击`、
   `AES/RSA加密通信特征`、`Web 进程派生 shell 进程` 等，`gatekeeper.py:81`）→ `IN_SCOPE_CONFIRMED`；
4. 通用进程名单独出现（`cmd.exe`、`powershell.exe`、`java.exe` 等，`gatekeeper.py:94`）→ `IN_SCOPE_WEAK`；
5. WebShell 弱关键词（`shell.aspx`、`文件上传`、`WebShell文件` 等，`gatekeeper.py:107`）→ `IN_SCOPE_WEAK`。

否定语义（`未发现/未检测到/不存在/排除/并非/不属于/no evidence/not detected/excluded/ruled out` 等，
`gatekeeper.py:156`）只作用于**同一分句**：同一分句中被否定的关键词不产生任何正向信号，
其他分句的确认证据不受影响（见边界用例 `BOUNDARY-NEG-*`）。

## 3. 三档判定组合（冻结）

| 信号组合 | 聚合强度 | 判定 | 知识工具行为 |
|---|---|---|---|
| 仅 `event_type=webshell` | `IN_SCOPE_WEAK` | `weak_signal` | 注册但只返回受限 `partial`，不返回确认性知识 |
| 强证据 + 弱证据 | `IN_SCOPE_CONFIRMED` | `in_scope` | 返回确认性知识 |
| 仅弱证据 / 仅通用进程名 | `IN_SCOPE_WEAK` | `weak_signal` | 同上 |
| 仅域外证据（域外优先于通用进程词） | `OUT_OF_SCOPE` | `out_of_scope` | 不注册知识工具 |
| 强证据 与 域外/良性证据并存 | `MIXED` | `weak_signal` | 不得放行为 `in_scope` |
| 无任何信号 / 全空字段 | `INDETERMINATE` | `weak_signal` | 安全默认拒绝确认性知识 |

聚合与映射实现：`gatekeeper.py:463`（`_aggregate_strength`）、`gatekeeper.py:260`（`_to_gate_decision`）。

## 4. 空、缺失与冲突字段处理（冻结）

| 情形 | 处理 | 结果 |
|---|---|---|
| `event_type` 为空/空白/未知 | 不产生事件类型信号，记录输入质量问题 | 最弱退化为 `weak_signal` |
| `alerts` 与 `evidence` 均为空 | 记录“信号容器为空” | `INDETERMINATE` → `weak_signal` |
| 单条文本为空串/空白/`None` | 不匹配任何关键词，不产生信号 | 不影响其他条目 |
| 某字段本身缺失 | 按 `SecurityEventInput` 默认值处理（空值） | 与显式空值一致 |
| `event_type=WebShell` 但正文明确排除 | 按否定语义不产生正向文本信号；事件类型仍保留弱信号 | `weak_signal`，不升级 |
| `event_type=WebShell` 但正文指向域外攻击 | 域外信号优先，并记录“事件类型与证据冲突” | `out_of_scope` |
| 确认级与域外/良性证据并存 | 记录输入质量冲突 | `MIXED` → `weak_signal` |
| 门禁结果缺失或审计异常 | 桥接与 CLI 均不注册知识工具，工具层再次拒绝 | 禁止 fail-open |

同一输入的判定必须与字段遍历顺序无关：判定是集合聚合，不做“随机取一个字段”。

## 5. 待冻结项（冻结方确认清单）

| 编号 | 事项 | 现状与复现 | 影响 | 建议处理 |
|---|---|---|---|---|
| D1 | `supporting_evidence_refs` 与 `evidence_summaries` 的对应关系 | **已实现（v1.1 关闭）**：`SecurityEvent.alert_summaries / evidence_summaries` 改为以引用 ID 为键的映射，桥接按 ID 查表拼串，无摘要证据保留裸 ID（`38cee87 fix: address PR50 review findings`）。验证：`tests/test_event_field_signal_contract.py::TestEvidencePairingById` 两条用例覆盖“新的在前”入参顺序与空摘要两种错位场景，v1.0 时为 xfail，v1.1 转为通过 | 已消除证据串位风险 | 无（后续若改变映射结构需升版本号） |
| D2 | 真实 XDR 路径的 `evidence` 摘要语义 | XDR/JSONL 适配器的证据摘要为 `"XDR 字段引用: xxx"` / `"标准化字段引用: xxx"`，无语义内容；实测真实 XDR 形态事件只能到 `weak_signal` | 企业真实告警链路上知识库不返回确认性知识 | 在适配器证据摘要中带 `alert_name` / `threatTypeDesc` / `description`，或明确接受该限制并写入文档 |
| D3 | 桥接与门禁测试的环境隔离 | 部分测试直接调用真实 `load_config()`，`KNOWLEDGE_MODE` 被设置为非法值时会失败 | 开发机环境不同会导致非确定性失败 | 统一用 `mock.patch.dict(os.environ, ...)` 固定环境 |
| D4 | `w3wp.exe` 单独出现仍是强确认 | `WEBSHELL_STRONG_CONFIRM_KEYWORDS` 保留 `w3wp.exe`（IIS 工作进程），其余通用进程名已降为弱信号 | 单独一条 “w3wp.exe” 文本即可判 `in_scope` | 由双方确认保留或一并降级，需在 v1.1 记录结论 |

## 6. 版本与签署

| 版本 | 日期 | 登记（陈敏） | 冻结（杨嘉琪） | 变更内容 |
|---|---|---|---|---|
| v1.0 | 2026-09-13 | 已登记 | 待确认 | 首版：字段来源表、信号来源与强度、三档判定组合、空/缺失/冲突处理、待冻结项 D1—D4 |
| v1.1 | 2026-09-13 | 已登记 | D1 已确认实现 | 对齐 `main@0001bbd`：`alert_summaries` / `evidence_summaries` 改为按引用 ID 建映射（D1 关闭），合同测试由 2 条 xfail 转为通过。**同版修正 §1 字段面**：原文把 `summary` 标为“门禁可读”有误——`summary` 不进入 `SecurityEventInput`（13 字段）、也不在门禁白名单（10 字段），门禁不可读；“不得用 `summary` 反推 `event_type`”属 bridge 之前的义务。新增 4 条字段面一致性用例锁定该结论。D2—D4 仍待杨嘉琪确认 |
