# spark-sec-agent-be

安全事件智能处置后端项目。系统目标是围绕一个安全事件建立统一处理主链：从告警接入、告警关联、风险研判、深度调查、处置决策、人工审批、执行处置到结果验证，形成可演示、可扩展、可替换平台能力的后端骨架。

当前版本是 MVP 开发框架，不是完整生产系统。真实 XDR OpenAPI、MCP、FastGPT/OpenClaw、真实处置动作等能力还没有接入，代码中先保留统一接口边界，并提供固定样例用于演示主流程。

## 系统当前做什么

- 使用统一 `EventContext` 承载一次安全事件处理过程中的状态、阶段结果、证据引用、时间线和错误信息。
- 使用状态机约束安全事件只能按合法路径流转，避免绕过研判、审批和验证。
- 使用固定 WebShell 样例模拟告警输入，便于在没有真实平台时演示主链。
- 使用模块化目录拆分后端职责，方便后续同学分别接入告警、研判、调查 Agent、平台工具、处置和前端接口。
- 数据库方向已确定为 MySQL，当前已提供 MySQL repository 和最小表结构；默认仍可使用内存存储进行本地演示。

## 最小主流程

主流程按以下阶段组织：

```text
固定样例告警
  -> 告警接入
  -> 告警关联
  -> 风险研判
  -> 深度调查 Agent
  -> 处置决策
  -> 人工审批
  -> 有状态 Mock 执行
  -> 独立验证
  -> 完成
```

对应状态线：

```text
RECEIVED
  -> CORRELATING
  -> TRIAGED
  -> INVESTIGATING
  -> DECISION_READY
  -> APPROVAL_REQUIRED
  -> EXECUTING
  -> VERIFYING
  -> COMPLETED
```

异常或证据不足时会进入：

```text
HUMAN_REQUIRED
FAILED
```

## 主要目录

```text
src/sec_agent/
  api/                  HTTP 应用与路由
  bootstrap/            依赖装配
  core/                 配置读取
  domain/               领域模型、统一上下文、状态机
  infrastructure/mysql/ MySQL 表模型和连接会话
  platforms/            平台接入适配层
  repositories/         持久化抽象、内存实现、MySQL 实现
  scripts/              本地命令脚本
  services/             告警接入、关联、研判、调查、处置、验证和编排
```

## 文档入口

- [系统开发与运行说明](docs/deliverables/system-development-and-operation-guide.md)
- [仓库提交规则](docs/deliverables/仓库提交规则.md)
