# 事件字段—来源—信号强度合同（v1.0）

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 合同名称 | 事件字段—来源—信号强度合同 |
| 版本号 | **v1.0**（登记方与冻结方共用同一个版本号） |
| 登记（信号语义） | 陈敏，告警关联模块，2026-09-13 |
| 冻结（代码接口确认） | 杨嘉琪，门禁与主链接口 —— **状态：待冻结确认** |
| 适用代码基线 | PR #50 头 `ae5aea0`（门禁与字段扩展尚未合入 `main`；合入后本合同的基线改记 `main` 对应提交） |
| 门禁实现 | `src/sec_agent/services/gatekeeper.py` |
| 字段生产 | `src/sec_agent/services/correlation.py`、`src/sec_agent/services/triage.py` |
| 桥接 | `src/sec_agent/services/deep_agent_bridge.py::_to_deep_agent_input` |
| 代码一致性测试 | `tests/test_event_field_signal_contract.py` |
| 门禁边界测试 | `tests/test_gatekeeper_boundary.py` |

本合同不是第二套设计文档：它只回答“主链到底如何理解这些字段”。字段来源、信号的语义由登记方负责；
接口是否真的按该语义实现由冻结方确认。任何一方改动字段来源或判定语义，必须同时升版本号并重跑上述两份测试，
不允许只改代码或只改文档。

## 1. 字段来源

| 字段 | 产生位置 | 语义 | 门禁是否可读 | 为空 / 缺失时 |
|---|---|---|---|---|
| `event_id` | `AlertCorrelationService.correlate` | 事件标识 | 可读（仅用于输入质量检查） | 记录“必填字段为空或非法” |
| `event_type` | `correlate()` 取同一事件内已校验一致的 `alert_type`（`correlation.py:71`） | **机器事件类型 token**（`webshell` / `sql_injection` / `lateral_movement` / `unauthorized_access` / `other`） | 可读，只作弱信号 | 不产生事件类型信号，按第 4 节降级 |
| `summary` | `correlate()` | 面向人的压缩摘要句 | 可读但**不得用于反推 `event_type`** | 记录输入质量问题 |
| `alert_refs` | `correlate()`，取 `AlertRecord.alert_id`（真实 XDR `uuId`） | 审计定位锚点 | 不作为语义字段，只作为文本载体 | 与 `alert_summaries` 同步缺失 |
| `alert_summaries` | `correlate()`，取 `AlertRecord.name`（`correlation.py:72`） | 与 `alert_refs` **同长同序**的告警名称 | 可读（文本信号） | 该条只保留 ID |
| `supporting_evidence_refs` | `RiskTriageService.triage`，按**入参告警顺序**展开 `evidence_refs.ref_id`（`triage.py:48`） | 证据定位锚点 | 不作为语义字段，只作为文本载体 | 无证据时为空列表 |
| `evidence_summaries` | `correlate()`，按 **`occurred_at` 升序**展开 `evidence_refs.summary` 并**过滤空摘要**（`correlation.py:73`） | 与 `supporting_evidence_refs` **必须按 `ref_id` 一一对应** | 可读（文本信号） | 该条只保留 ID |
| `triage.verdict` | 风险研判模块 | 结构化研判结论（`malicious` / `benign` / `uncertain`） | 可读 | 不产生研判信号 |
| `initial_verdict` | 上游初步研判文本 | 初步结论文本 | 可读 | 不产生研判信号 |
| `confidence` / `trace_id` / `run_id` | 上游 | 置信度与链路标识 | **禁止读取**（不在白名单） | 与判定无关 |

桥接把带摘要的引用拼成 `<ref_id>: <摘要>` 交给门禁与 Agent；只有 ID 没有摘要时保留裸 ID。

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
| D1 | `supporting_evidence_refs` 与 `evidence_summaries` 的对应关系 | 桥接 `_described_refs`（`deep_agent_bridge.py:198`）按**位置**配对，而两份列表分别来自 `occurred_at` 升序（correlation）与入参顺序（triage），且 correlation 会过滤空摘要。`tests/test_event_field_signal_contract.py` 中两条 xfail 用例可稳定复现串位 | 证据归属错标，直接影响原始证据引用与门禁文本判定 | 改为 `ref_id → summary` 映射后按 ID 拼串；空摘要只保留 ID |
| D2 | 真实 XDR 路径的 `evidence` 摘要语义 | XDR/JSONL 适配器的证据摘要为 `"XDR 字段引用: xxx"` / `"标准化字段引用: xxx"`，无语义内容；实测真实 XDR 形态事件只能到 `weak_signal` | 企业真实告警链路上知识库不返回确认性知识 | 在适配器证据摘要中带 `alert_name` / `threatTypeDesc` / `description`，或明确接受该限制并写入文档 |
| D3 | 桥接与门禁测试的环境隔离 | 部分测试直接调用真实 `load_config()`，`KNOWLEDGE_MODE` 被设置为非法值时会失败 | 开发机环境不同会导致非确定性失败 | 统一用 `mock.patch.dict(os.environ, ...)` 固定环境 |
| D4 | `w3wp.exe` 单独出现仍是强确认 | `WEBSHELL_STRONG_CONFIRM_KEYWORDS` 保留 `w3wp.exe`（IIS 工作进程），其余通用进程名已降为弱信号 | 单独一条 “w3wp.exe” 文本即可判 `in_scope` | 由双方确认保留或一并降级，需在 v1.1 记录结论 |

## 6. 版本与签署

| 版本 | 日期 | 登记（陈敏） | 冻结（杨嘉琪） | 变更内容 |
|---|---|---|---|---|
| v1.0 | 2026-09-13 | 已登记 | 待确认 | 首版：字段来源表、信号来源与强度、三档判定组合、空/缺失/冲突处理、待冻结项 D1—D4 |
