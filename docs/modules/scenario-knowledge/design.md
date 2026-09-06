# 场景知识模块设计
负责人: design

## 模块职责

围绕主场景沉淀攻击原理、常见特征、调查步骤、误报情况、处置建议和资料来源。

## 输入输出

- 输入：场景名称、事件摘要、证据缺口。
- 输出：知识引用、调查建议、处置建议。

## 安全边界

- 不编造知识来源。
- 不把未经脱敏的平台原始内容写入知识库。

## 待补充

- 主场景最终确认。
- 知识包结构。
- RAG 或 FastGPT 知识库接入方式。

## 今日新增 (2026-09-06)
### 1. 信号门禁 (Security Gate) 定义
为确保深度调查 Agent 的输入质量，定义门禁机制过滤并标准化输入信号。

#### 字段读取约束
- **允许读取 (Signals)**: `event_type`, `alerts`, `evidence`, `triage`。
- **允许读取 (Context)**: `source_ip`, `target_ip`, `severity`, `timestamp`。
- **禁止提取信号**: `trace_id`, `run_id`, `initial_verdict` (防止预设偏见)。

#### 信号转换规则
1. **强信号 (Confirmed WebShell)**: 包含进程链异常 (如 `w3wp.exe -> cmd.exe`)、高危函数调用 (如 `eval`) 且具备明确恶意上下文。
2. **弱信号 (Weak Signal)**: 仅文件名可疑、合法 Base64 业务、单次上传行为。此类信号触发 `weak_signal` 状态，要求 Agent 补充证据。
3. **非 WebShell 信号**: 明确的域外事件 (如 SSH 爆破) 或已知业务合法流量。

