# 正式事件上下文、门禁与知识工具合同（正式冻结 v1.1）

> 主干基线：`main@0001bbd`（PR #50 已合并）
> 整合来源：PR #54 `c9b5c845` + PR #55 `647da763`
> 候选分支：`codex/pr54-pr55-integration-0913`（仅本地，未推送）
> 状态：项目负责人于2026-09-14基于交付时限、安全默认和本地组合回归结果裁决正式冻结；不再等待个人补充回执。最终Commit待交付提交时登记，不影响本版语义冻结。
> 目标：冻结外部调用者必须遵守的事件输入、门禁三档、知识工具可用性和调用结果语义。

## 1. 职责边界

- 陈敏：确认事件字段来源、信号含义和强度边界。
- 杨嘉琪：确认门禁、bridge、工具注册和五态实现与本合同一致。
- 杨景凡：按同一合同绑定Agent，不复制门禁或另建模式开关。
- 李雨妍：按同一合同接入主链、评测和汇总。

本文件是唯一规范性合同。三方交接单、RC说明及字段登记附件只作追溯，不得另行定义冲突语义。2026-09-14之后的实现必须遵守本冻结版；最终交付提交完成后补登记Commit。

## 2. Agent标准输入

`SecurityEventInput`当前共有13个字段：

| 字段 | 类型 | 正式语义 | 门禁可读 |
|---|---|---|---|
| `event_id` | `str` | 稳定事件ID | 是 |
| `event_type` | `str` | 结构化事件类型 | 是 |
| `severity` | `str` | 兼容字段名；bridge当前填入`triage.priority.upper()`，表示研判优先级标签，不是XDR原始`severity`、`AlertRecord.raw_severity`或数值型`risk_score` | 是 |
| `timestamp` | `str` | 事件时间；bridge当前取`first_seen_at` | 是 |
| `source_ip` | `str` | 攻击源；未知时允许空 | 是 |
| `target_ip` | `str` | 目标地址或资产；未知时允许空 | 是 |
| `alerts` | `list[str]` | 告警ID及可选摘要的序列化列表 | 是 |
| `evidence` | `list[str]` | 支持证据ID及可选摘要的序列化列表 | 是 |
| `initial_verdict` | `str` | 上游初步研判，不等于最终攻击类型 | 是 |
| `confidence` | `float` | 上游置信度，供Agent参考 | 否 |
| `triage` | `dict`或`None` | 上游研判完整结构 | 是 |
| `trace_id` | `str` | 全链路追踪ID | 否 |
| `run_id` | `str` | 本次运行ID | 否 |

门禁白名单固定为：

```text
event_id, event_type, severity, timestamp, source_ip, target_ip,
alerts, evidence, triage, initial_verdict
```

`confidence`、`trace_id`、`run_id`可以进入Agent上下文，但不得参与知识门禁判断。

正式调用方应完整提供13个字段；`alerts/evidence`必须为列表。必填语义字段为空、两类信号容器同时为空或字段类型错误时必须记录输入质量问题，并按最弱`weak_signal`或`blocked_by_gate`安全降级，不得异常放行。

## 3. event_type与引用/摘要绑定

### 3.1 event_type

正式链路：

```text
SecurityEvent.event_type
→ DeepAgentBridge._to_deep_agent_input()
→ SecurityEventInput.event_type
```

- 只读取结构化`event.event_type`。
- 禁止从`SecurityEvent.summary`、告警ID或自由文本猜测事件类型。
- `SecurityEvent.summary`只用于人类阅读，不替代机器契约字段，也不作为门禁新增证据。

### 3.2 告警

上游结构：

```text
alert_refs: [alert_id, ...]
alert_summaries: {alert_id: summary, ...}
```

bridge按`alert_id`查找摘要，并序列化为：

```text
有摘要："<alert_id>: <summary>"
无摘要："<alert_id>"
```

最终传给Agent的`alerts`类型是`list[str]`，不是位置对齐的两个数组，也不是摘要字典。

### 3.3 支持证据

上游结构：

```text
supporting_evidence_refs: [evidence_ref_id, ...]
evidence_summaries: {evidence_ref_id: summary, ...}
```

bridge按`ref_id`查找摘要，并用与告警相同的规则序列化到`evidence: list[str]`。缺摘要时只保留原ID；禁止按两个列表的数组位置拼接。

## 4. 门禁三档

正式三档只有：

```text
in_scope
weak_signal
out_of_scope
```

- `in_scope`：`guarded`模式注册`knowledge_query`，允许返回结构化`KnowledgeCard`。
- `weak_signal`：注册`knowledge_query`，但调用只返回受限结果，不返回确认性知识正文。
- `out_of_scope`：正式CLI/bridge不注册`knowledge_query`。
- gate缺失、无效或异常：fail-closed，不注册知识工具，不默认按`in_scope`放行。

### 4.1 信号来源与强度

门禁只读取第2节的10个白名单字段，`SecurityEvent.summary`不进入门禁。每条信号必须记录来源：`event_type/alerts/evidence/triage/initial_verdict`。

内部信号强度为：`OUT_OF_SCOPE`、`BENIGN_LIKE`、`INDETERMINATE`、`IN_SCOPE_WEAK`、`IN_SCOPE_CONFIRMED`、`MIXED`。其中：

- 结构化`event_type=webshell`、`triage.verdict=malicious`和普通进程名只形成弱信号；
- 单独出现`cmd.exe/powershell.exe/java.exe/w3wp.exe`不得确认WebShell；
- “Web进程派生Shell进程”等WebShell专属组合证据才可形成确认信号；
- 内核驱动、Rootkit、SSH暴力破解等域外证据优先判为域外；
- “未发现、未检测到、排除、并非、不属于”等否定仅作用于同一分句，被否定关键词不产生正向信号；
- 强确认与域外/良性证据并存时为`MIXED → weak_signal`；
- 全空、未知或无法确定时为`INDETERMINATE → weak_signal`。

真实XDR证据摘要只有字段定位而缺少语义正文时，不人为拼造确认级证据；允许依靠结构化事件类型和告警摘要形成弱信号并继续补证。

## 5. 工具可用性与调用五态必须分层

### 5.1 注册前可用性状态

没有注册工具时不会产生`ToolResult`，因此不得把所有“registry中无工具”统计为`REFUSED`。

| 可用性 | 含义 |
|---|---|
| `available` | `guarded`且gate为`in_scope/weak_signal`，工具已注册 |
| `disabled_by_mode` | `KNOWLEDGE_MODE=off`，按实验配置主动关闭 |
| `blocked_by_gate` | `out_of_scope`、gate缺失、无效或异常，按安全边界不注册 |

代码载体为`KnowledgeToolAvailability`、`ToolAvailabilityRecord`和`resolve_knowledge_tool_availability()`。CLI与`DeepAgentBridge`必须调用同一分类函数，并由`ToolRegistry.availability_of("knowledge_query")`保留判定与原因；不得再分别复制条件判断。

### 5.2 实际调用后的五态

只有工具已注册且实际调用后，才判定以下五态。

#### SUCCESS

```text
status = success
error = ""
data.knowledge_returned = true
```

命中正式知识卡。`source_citations`仅是知识来源，不是当前事件证据；代码侧独立记录为`tool_call_records[].knowledge_citations`。

#### EMPTY

```text
status = failed
error = knowledge_not_found
retryable = false
data.knowledge_returned = false
```

查询合法但没有匹配卡，不是超时、系统错误或门禁拒绝。同词不自动重试，继续使用事件证据、MCP或其他工具。

#### REFUSED

`weak_signal`正式调用返回：

```text
status = partial
data.knowledge_returned = false
data.restriction = confirmatory_knowledge_blocked
```

工具被直接实例化时仍保留防御性错误：

```text
knowledge_scope_mismatch
missing_knowledge_gate_decision
invalid_knowledge_gate_decision
```

正式CLI/bridge中的`out_of_scope`、gate缺失、无效或异常通常表现为`blocked_by_gate`且工具不注册，而不是一次工具返回。

#### TIMEOUT

```text
status = failed
error = knowledge_timeout
retryable = true
data.knowledge_returned = false
```

允许受控重试，不得无限重试；关键补证持续超时且证据不足时转人工。

#### INTERNAL_ERROR

```text
status = failed
error = knowledge_internal_error
retryable = false
data.knowledge_returned = false
```

不自动重试；继续其他工具，关键补证失败且证据不足时转人工。

### 5.3 五态之外的协议错误

```text
status = failed
error = empty_knowledge_query
```

它表示调用参数为空，属于`INVALID_REQUEST`，不属于`EMPTY`，也不得计入门禁`REFUSED`。评测中应单列为参数错误。

### 5.4 判定顺序

```text
1. 先判断工具可用性：available / disabled_by_mode / blocked_by_gate
2. 若实际调用：
   - empty_knowledge_query → INVALID_REQUEST（五态之外）
   - status=success → SUCCESS
   - status=partial 且 restriction=confirmatory_knowledge_blocked → REFUSED
   - knowledge_not_found → EMPTY
   - knowledge_timeout → TIMEOUT
   - knowledge_internal_error → INTERNAL_ERROR
   - missing/invalid/scope mismatch → REFUSED（仅防御性直接调用路径）
```

外部调用者不得只看`status=failed`判断业务含义。

## 6. 知识引用与事件证据隔离

- `source_citations`说明知识卡依据哪些规范或资料。
- 当前事件证据来自告警、日志和真实调查工具结果。
- 知识来源不得写入当前事件的`key_evidence`或`evidence_source`。
- Agent工具记录使用独立字段：

```json
{
  "tool": "knowledge_query",
  "status": "success",
  "knowledge_citations": {
    "urls": ["..."],
    "levels": ["..."]
  }
}
```

- fallback报告也不得把知识卡摘要、URL或等级提升为当前事件事实。
- 正常LLM报告路径不得信任模型自行填写的`key_evidence/evidence_source`；代码必须用上游事件证据与非知识工具的成功/部分成功结果覆盖这两个字段。
- 只有`knowledge_query`成功而没有事件观测工具成功时，不得据此通过正常报告路径形成事件结论，应降级为证据不足并人工接管。

## 7. 正式冻结记录

项目负责人已于2026-09-14裁决采用以下统一口径，不再把个人补充回执作为阻塞项。此处的完成表示“合同语义与本地实现已核对”，不表示真实XDR/MCP/LLM平台验收已经完成。

```text
[x] 13个输入字段、来源和信号语义已由字段面测试锁定
[x] 门禁10字段白名单已由机械一致性测试锁定，summary不可读
[x] initial_verdict/triage不得把任意malicious事件升级为WebShell
[x] event_type只走结构化字段
[x] alert_refs ↔ alert_summaries按alert_id映射
[x] supporting_evidence_refs ↔ evidence_summaries按ref_id映射
[x] 注册前available/disabled_by_mode/blocked_by_gate三态已有代码载体；调用后五态沿用冻结合同
[x] 正常LLM与fallback两条路径均有确定性知识引用隔离
[x] D2正式关闭：真实XDR证据摘要不足时保持weak_signal并继续补证，禁止拼造或补强证据
[x] D3正式关闭：合同测试显式隔离KNOWLEDGE_MODE环境变量
[x] D4正式关闭：单独w3wp.exe仅为弱信号；同分句Web宿主派生shell复合链才可确认
[ ] 交付提交完成后登记最终Commit（仅交付记录，不阻塞语义冻结）
```

冻结验证：定向回归156 passed / 1 skipped；纳入PR55最新字段面测试与`main@0001bbd`修订后，全量350 passed / 1 skipped。该结果是本地自动化组合回归，不替代真实平台联调。
