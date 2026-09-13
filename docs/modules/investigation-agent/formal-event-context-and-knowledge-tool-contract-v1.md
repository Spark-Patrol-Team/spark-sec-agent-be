# 正式事件上下文与知识工具合同（冻结候选 v1.1）

> 基线：`main@9247624`（PR #50 已合并）
> 候选分支：`fix/knowledge-citation-contract-v1`
> 状态：待陈敏确认输入与信号语义、杨嘉琪确认接口实现后，改为“正式冻结 v1”并登记最终Commit。
> 目标：冻结外部调用者必须遵守的事件输入、门禁三档、知识工具可用性和调用结果语义。

## 1. 职责边界

- 陈敏：确认事件字段来源、信号含义和强度边界。
- 杨嘉琪：确认门禁、bridge、工具注册和五态实现与本合同一致。
- 杨景凡：按同一合同绑定Agent，不复制门禁或另建模式开关。
- 李雨妍：按同一合同接入主链、评测和汇总。

本合同的“确认”必须指向同一文件和同一Commit；不得分别维护内容不同的私发版本。

## 2. Agent标准输入

`SecurityEventInput`当前共有13个字段：

| 字段 | 类型 | 正式语义 | 门禁可读 |
|---|---|---|---|
| `event_id` | `str` | 稳定事件ID | 是 |
| `event_type` | `str` | 结构化事件类型 | 是 |
| `severity` | `str` | 风险等级 | 是 |
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

当前门禁输入质量要求：`event_id/event_type/timestamp`不得为空，`alerts/evidence`必须为列表且不能同时为空。正式调用方应完整提供13个字段；允许为空的字段仍须遵守上表类型。

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

## 5. 工具可用性与调用五态必须分层

### 5.1 注册前可用性状态

没有注册工具时不会产生`ToolResult`，因此不得把所有“registry中无工具”统计为`REFUSED`。

| 可用性 | 含义 |
|---|---|
| `available` | `guarded`且gate为`in_scope/weak_signal`，工具已注册 |
| `disabled_by_mode` | `KNOWLEDGE_MODE=off`，按实验配置主动关闭 |
| `blocked_by_gate` | `out_of_scope`、gate缺失、无效或异常，按安全边界不注册 |

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

## 7. 正式冻结确认

以下项目全部确认后，才能把标题从“冻结候选 v1.1”改为“正式冻结 v1”：

```text
[ ] 陈敏确认13个输入字段、来源和信号语义
[ ] 陈敏确认门禁10字段白名单不再扩张
[ ] 陈敏确认initial_verdict/triage不会把任意malicious事件升级为WebShell
[ ] 杨嘉琪确认event_type只走结构化字段
[ ] 杨嘉琪确认alert_refs ↔ alert_summaries按alert_id映射
[ ] 杨嘉琪确认supporting_evidence_refs ↔ evidence_summaries按ref_id映射
[ ] 杨嘉琪确认注册前可用性与调用后五态分层
[ ] 杨景凡、李雨妍登记同一文件与最终Commit
```
