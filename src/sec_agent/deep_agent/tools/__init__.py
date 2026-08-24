# -*- coding: utf-8 -*-
"""工具适配层：统一工具接口 + Mock 工具 + 可选 MCP 客户端。"""
from .base import Tool, ToolResult, ToolRegistry
from .mock import build_mock_tools


def __getattr__(name: str):
    if name in {"MCPClient", "MCPTool", "build_mcp_tools"}:
        from .mcp_client import MCPClient, MCPTool, build_mcp_tools

        values = {
            "MCPClient": MCPClient,
            "MCPTool": MCPTool,
            "build_mcp_tools": build_mcp_tools,
        }
        return values[name]
    raise AttributeError(name)

__all__ = [
    "Tool", "ToolResult", "ToolRegistry",
    "build_mock_tools",
    "MCPClient", "MCPTool", "build_mcp_tools",
]
