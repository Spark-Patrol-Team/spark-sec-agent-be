# -*- coding: utf-8 -*-
"""工具适配层：统一工具接口 + Mock 工具 + MCP 客户端。"""
from .base import Tool, ToolResult, ToolRegistry
from .mock import build_mock_tools
from .mcp_client import MCPClient, MCPTool, build_mcp_tools

__all__ = [
    "Tool", "ToolResult", "ToolRegistry",
    "build_mock_tools",
    "MCPClient", "MCPTool", "build_mcp_tools",
]
