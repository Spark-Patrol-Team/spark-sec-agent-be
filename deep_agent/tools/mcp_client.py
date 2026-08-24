# -*- coding: utf-8 -*-
"""最小 MCP 客户端（streamable HTTP 传输），连接深信服 MCP 服务。

不依赖官方 mcp SDK，用 requests 实现 JSON-RPC 2.0 over HTTP。
说明：四个集群内部地址（mcp-server.platform.svc.cluster.local）在本地无法连通，
会自动连接失败并跳过；公网「漏洞信息查询」配置 MCP_API_KEY 后可用。
"""
from __future__ import annotations

import json
from typing import Any, Optional

import requests

from .base import Tool, ToolResult
from ..config import ToolConfig


def _parse_body(resp: requests.Response) -> Any:
    """兼容 JSON 与 SSE（text/event-stream）两种响应。"""
    ctype = resp.headers.get("Content-Type", "")
    # MCP 响应固定 UTF-8；requests 对无 charset 的 text/event-stream 会误用 latin-1，
    # 使中文乱码并产生伪换行符，这里显式按 UTF-8 解码。
    text = resp.content.decode("utf-8", errors="replace")
    if "text/event-stream" in ctype:
        # 提取所有 data: 行，取最后一段 JSON
        payloads = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
        for p in reversed(payloads):
            if p and p != "[DONE]":
                try:
                    return json.loads(p)
                except json.JSONDecodeError:
                    continue
        raise ConnectionError(f"MCP SSE 无有效数据: {text[:200]}")
    return json.loads(text)


class MCPClient:
    def __init__(self, url: str, api_key: str = "", timeout: int = 20):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.session_id: Optional[str] = None
        # 禁用系统代理：MCP 服务为内网直连/公网直连，走本地 Clash 等代理会 ReadTimeout（实测）。
        self._session = requests.Session()
        self._session.trust_env = False

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
            h["apikey"] = self.api_key
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _rpc(self, method: str, params: Optional[dict] = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        resp = self._session.post(self.url, json=payload, headers=self._headers(), timeout=self.timeout)
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if resp.status_code != 200:
            raise ConnectionError(f"MCP HTTP {resp.status_code}: {resp.text[:200]}")
        data = _parse_body(resp)
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result") if isinstance(data, dict) else data

    def initialize(self) -> Any:
        return self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "deep-investigation-agent", "version": "0.1.0"},
        })

    def list_tools(self) -> list[dict]:
        result = self._rpc("tools/list", {})
        return (result or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


def _extract_text(result: Any) -> str:
    """从 MCP tools/call 返回里提取文本。"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            return "\n".join(texts)
        if "structuredContent" in result:
            return json.dumps(result["structuredContent"], ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


class MCPTool(Tool):
    """把 MCP 工具包装成统一 Tool 接口。"""

    def __init__(self, client: MCPClient, name: str, description: str, input_schema: dict):
        self._client = client
        self.name = name
        self.description = description
        # MCP inputSchema 即 JSON Schema，直接作为 OpenAI function 参数
        self.parameters = input_schema or {"type": "object", "properties": {}}

    def call(self, params):
        try:
            result = self._client.call_tool(self.name, params)
            return ToolResult(summary=_extract_text(result))
        except Exception as e:  # noqa: BLE001
            return ToolResult(status="failed", error=f"{type(e).__name__}: {e}", summary="MCP 调用失败")


def build_mcp_tools(config: ToolConfig, on_error=None) -> list[Tool]:
    """遍历配置的 MCP 地址，连接并列出工具，包装为统一 Tool。连不上的跳过。"""
    tools: list[Tool] = []
    for label, url in config.mcp_urls.items():
        try:
            client = MCPClient(url, api_key=config.mcp_api_key, timeout=config.mcp_timeout)
            client.initialize()
            for t in client.list_tools():
                tools.append(MCPTool(
                    client=client,
                    name=t.get("name", ""),
                    description=t.get("description", "")[:2000],
                    input_schema=t.get("inputSchema", {}),
                ))
        except Exception as e:  # noqa: BLE001
            msg = f"[warn] MCP 服务「{label}」连接失败，跳过：{type(e).__name__}: {e}"
            if on_error:
                on_error(msg)
    return tools
