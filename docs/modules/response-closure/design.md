# 处置闭环模块设计

## 0. 文档信息

| 项目 | 内容 |
|---|---|
| 模块 | response-closure |
| 本轮任务 | T0913：最终响应闭环完善、语义验收与交付准备 |
| 文档职责 | 设计目标、责任边界、数据语义、安全规则和闭环判定原则 |
| 能力性质 | 自研编排与本地 Stateful Mock；真实平台设备生效尚未被当前测试证明 |

## 1. 设计目标与责任边界

处置闭环模块承接调查结果，形成候选 ResponsePlan，经过审批门禁后调用统一工具契约执行，并通过独立验证决定最终处置结果。

模块负责：

- 消费上游结构化调查结果和 TriageResult；
- 按确定性规则冻结 response_evidence_scope；
- 根据冻结范围生成或拒绝 ResponsePlan；
- 处理风险级别、审批、执行结果和独立验证结果；
- 将无法安全判断或证明的情况转为人工接管。

模块不负责：

- 重新定义调查结论或知识库结论；
- 将模型建议直接转换为真实平台授权；
- 实现真实平台的封禁、隔离或设备联动能力；
- 以平台请求成功、平台记录或 Mock 记录替代设备生效证据。

## 2. response_evidence_scope 单一责任

response_evidence_scope 的责任边界固定如下：

| 角色 | 唯一位置 | 责任 |
|---|---|---|
| 生产者 | ResponseEvidenceScopeResolver.resolve() | 在调查完成后按确定性规则产出 IN_SCOPE、WEAK_SIGNAL 或 OUT_OF_SCOPE |
| 主链承载 | Orchestrator.start() | 将 resolver 返回值写入 ctx.triage.response_evidence_scope，并保存上下文 |
| 业务消费者 | ResponseDecisionService._boundary_decision() | 只消费 triage.response_evidence_scope 决定是否允许生成方案 |

ResponseDecisionService 不重新计算 scope。其对 evidence_gaps、未决问题和调查工具失败的检查，是对“已冻结 scope 与当前调查状态一致性”的 fail-closed 校验；发现不一致时收紧决策，不产生新的 scope。

范围语义：

- IN_SCOPE：当前 WebShell 证据范围满足候选处置边界，仍须经过风险和审批门禁；
- WEAK_SIGNAL：证据不足、工具失败或存在调查缺口，只允许继续调查或人工接管；
- OUT_OF_SCOPE：明确不属于当前 WebShell 自动处置范围，不生成 WebShell 处置方案。

gate_decision 与 response_evidence_scope 是不同字段。前者属于正式 WebShell 信号门禁，后者是主链处置授权边界；两者不等价，但前者构成后者的硬上限：out_of_scope 只能得到 OUT_OF_SCOPE，weak_signal 只能得到 WEAK_SIGNAL，只有 in_scope 才能继续接受调查完整性、原始证据数量和工具结果校验。响应层不再维护第二套 WebShell 关键词表。knowledge refs 只是知识依据，不能替代原始处置证据；知识查询成功也不会自动升级 scope。

## 3. 闭环数据与安全规则

主链承载的核心对象为：

- TriageResult.response_evidence_scope：冻结后的处置证据范围；
- ResponsePlan.evidence_scope：生成方案时复制并留存的范围快照；
- ToolRequest / ToolResult：统一执行和验证工具调用契约；
- ExecutionResult：执行调用结果，包含 executed、调用状态、运行模式和执行层级；
- VerificationResult：独立验证状态、验证证据层、证据引用和最终业务状态。

满足正式门禁 IN_SCOPE 且通过调查完整性校验的固定样例，其候选动作是 stateful_mock_containment，目标取调查结果中的第一个 affected_objects。只有 WebShell 告警名称或 event_type、没有确认级证据的 JSONL/XDR 输入停在 WEAK_SIGNAL 和人工复核，不生成候选动作。动作建议不是授权；中、高、严重风险动作需要人工审批。

闭环顺序为：

~~~text
Investigation
  -> response_evidence_scope production
  -> TriageResult
  -> ResponseDecisionService
  -> ResponsePlan
  -> Approval
  -> Execution
  -> Verification
  -> Final Disposition
~~~

安全规则：

1. 调查要求人工接管、没有受影响对象、没有建议动作或 scope 不满足时，不生成自动处置方案。
2. 高风险方案必须进入 APPROVAL_REQUIRED，审批拒绝进入 HUMAN_REQUIRED。
3. 执行工具成功只表示执行调用成功，不能直接表示动作生效。
4. 只有独立验证工具成功、验证状态为有效、动作状态为 effective/executed，且 verified_effect_layer=DEVICE_EFFECT 时，才允许处置链进入 COMPLETED。
5. Mock、PLATFORM_REQUEST 和 PLATFORM_RECORD 层均不能单独满足完成条件。

## 4. 五层证据语义

| 事实层 | 当前代码来源 | 当前可证明内容 | 不能推出 |
|---|---|---|---|
| 请求已发送 | 构造 ToolRequest 并调用 platform.run_tool() | 系统尝试发起了工具调用 | 平台已受理、已记录或设备已生效 |
| 平台已受理 | 当前无独立字段和平台回执契约 | 当前系统不对 platform accepted 做独立证明 | 不能由请求调用返回直接补写 |
| 平台记录成功 | ToolResult 输出或 Mock ledger 的记录结果 | 平台/本地账本存在一条记录 | 设备实际生效 |
| 设备实际生效 | verified_effect_layer=DEVICE_EFFECT 的验证结果 | 仅在有有效设备层证据时可作为生效证据 | 不能由 Mock/platform record 推导 |
| 独立验证成功 | response_verify 成功、有效动作状态和 DEVICE_EFFECT 的组合 | 满足响应闭环完成门槛 | 不能由执行工具自身成功替代 |

当前系统不对 platform accepted 做独立证明。当前真实平台也没有被本仓库测试证明能够提供独立的 platform recorded 或 device effect 证据；现有 DEVICE_EFFECT 仅由可控测试替身场景用于验证完成门槛。

## 5. 最终处置语义

- COMPLETED：响应处置链已执行，且独立验证证明设备效果层为 DEVICE_EFFECT。TRIAGED -> COMPLETED 的低风险分诊结束是另一种语义，不表示响应处置完成。
- FAILED：处置链或主流程出现明确失败，流程不能按当前路径继续，例如处置工具返回失败或执行结果为 executed=false。
- HUMAN_REQUIRED：系统在当前安全边界内无法自动判断或证明，例如 scope 不足、审批拒绝、验证工具失败、验证未知、动作未生效或缺少设备效果证据。

本轮不新增未知副作用状态、持久化状态模型、响应状态机或超时/重试/回滚机制。真实平台适配器若在请求发出后异常，当前实现仍可能按通用异常路径记为失败；这属于现有能力边界，不在 T0913 的本轮范围内。

## 6. Mock 与真实平台边界

StatefulMockLedger 用于本地执行和验证回归，执行工具与 response_verify 读取同一份进程内记录。Mock record、action_status=executed 或 PLATFORM_RECORD 只证明本地流程和记录语义，不证明真实设备已经生效。

当前真实高风险处置工具尚未接入。因而本模块可以证明“Mock 执行链按安全门槛运行”，不能宣称真实平台处置、设备生效或生产级独立验证已经完成。
