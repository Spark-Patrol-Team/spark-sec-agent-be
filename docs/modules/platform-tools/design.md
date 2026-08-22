# 平台工具模块设计

## 模块职责

封装 XDR OpenAPI、MCP、固定样例、FastGPT/OpenClaw 等平台能力，为业务模块提供统一工具调用入口。

## 输入输出

- 输入：`ToolRequest`。
- 输出：`ToolResult`。

## 安全边界

- 凭据不进入源码、日志、前端响应和上下文。
- 工具调用必须保留 `trace_id` 和 `idempotency_key`。
- 工具结果必须返回结构化错误和证据引用。

## 待补充

- XDR OpenAPI 映射。
- MCP 工具清单。
- FastGPT/OpenClaw 调用方式。
- 工具权限和风险分级。

