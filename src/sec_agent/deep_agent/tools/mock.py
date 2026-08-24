# -*- coding: utf-8 -*-
"""Mock 工具：真实平台不可用时保证调查闭环可运行（对应设计文档"MVP 开发阶段用 Mock"）。

每个 Mock 工具对应一类真实深信服 MCP 能力，输入输出语义对齐，替换为真实工具时 Agent 调用逻辑不变。
内置一份 WebShell 主场景模拟数据；未知 IP 返回"数据不可得"，用于演示"工具无数据 → 人工接管"边界。
"""
from __future__ import annotations

from .base import Tool, ToolResult

# ---- 模拟数据（key 为目标 IP）----
_MOCK_ASSETS = {
    "192.168.1.100": {
        "资产名称": "OA服务器",
        "资产类型": "服务器",
        "操作系统": "Linux",
        "重要程度": "高",
        "是否核心资产": True,
        "是否暴露互联网": False,
        "责任人": "张三",
    },
}

_MOCK_ALERTS = {
    "192.168.1.100": [
        {"名称": "WebShell通信行为告警", "风险等级": "高危", "攻击结果": "攻击成功", "处置状态": "待处置"},
        {"名称": "异常外联告警", "风险等级": "中危", "攻击结果": "攻击尝试", "处置状态": "待处置"},
    ],
}

_MOCK_VULNS = {
    "192.168.1.100": [
        {"漏洞名称": "OA系统任意文件上传漏洞", "风险等级": "高危", "修复优先级": "高"},
    ],
}


class MockAssetQuery(Tool):
    name = "query_asset"
    description = "查询目标 IP 对应的资产信息（资产名称、类型、重要程度、是否核心资产、是否暴露互联网）。"
    parameters = {
        "type": "object",
        "properties": {"ip": {"type": "string", "description": "资产 IP"}},
        "required": ["ip"],
    }

    def call(self, params):
        ip = params.get("ip", "")
        asset = _MOCK_ASSETS.get(ip)
        if not asset:
            return ToolResult(status="failed", summary="未查询到该 IP 的资产信息", error="数据不可得")
        return ToolResult(summary=f"资产信息：{asset}")


class MockAlertQuery(Tool):
    name = "query_alerts"
    description = "查询与目标 IP 相关的安全告警（告警名称、风险等级、攻击结果、处置状态）。"
    parameters = {
        "type": "object",
        "properties": {"ip": {"type": "string", "description": "资产 IP"}},
        "required": ["ip"],
    }

    def call(self, params):
        ip = params.get("ip", "")
        alerts = _MOCK_ALERTS.get(ip, [])
        if not alerts:
            return ToolResult(status="failed", summary="未查询到该 IP 的告警", error="数据不可得")
        return ToolResult(summary=f"告警列表：{alerts}")


class MockVulnQuery(Tool):
    name = "query_vulnerabilities"
    description = "查询目标 IP 关联的漏洞信息（漏洞名称、风险等级、修复优先级）。"
    parameters = {
        "type": "object",
        "properties": {"ip": {"type": "string", "description": "资产 IP"}},
        "required": ["ip"],
    }

    def call(self, params):
        ip = params.get("ip", "")
        vulns = _MOCK_VULNS.get(ip, [])
        if not vulns:
            return ToolResult(status="failed", summary="未查询到该 IP 的漏洞", error="数据不可得")
        return ToolResult(summary=f"漏洞列表：{vulns}")


class MockSecGPTAnalysis(Tool):
    name = "secgpt_analyze"
    description = "调用安全GPT对事件/告警做专业解读与研判，获取分析结论与处置建议。"
    parameters = {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "需要分析的事件或告警描述"}},
        "required": ["content"],
    }

    def call(self, params):
        content = params.get("content", "")
        head = content[:60]
        return ToolResult(
            summary=(
                f"[安全GPT研判] 针对「{head}」：结合攻击源与目标存在通信关系、目标为高价值业务服务器，"
                f"研判为疑似真实 WebShell 攻击，建议进一步检查 WebShell 文件及相关进程。"
            )
        )


class MockAttackDetect(Tool):
    name = "attack_detect"
    description = "对 HTTP 请求报文做攻击类型分类与攻击成功/失败判断。"
    parameters = {
        "type": "object",
        "properties": {"payload": {"type": "string", "description": "HTTP 请求报文或恶意 payload"}},
        "required": ["payload"],
    }

    def call(self, params):
        payload = params.get("payload", "")
        head = payload[:60]
        return ToolResult(
            summary=f"[攻击检测] 针对「{head}」：攻击类型=WebShell 上传/通信，攻击结果=攻击成功。"
        )


class MockVulnIntelligence(Tool):
    name = "vuln_intelligence"
    description = "查询漏洞情报（CVE/CNVD/CNNVD/深信服SF ID），获取漏洞详情与修复建议。"
    parameters = {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "漏洞关键词或编号"}},
        "required": ["keyword"],
    }

    def call(self, params):
        keyword = params.get("keyword", "")
        return ToolResult(
            summary=(
                f"[漏洞情报] 与「{keyword}」相关的漏洞情报：WebShell 类漏洞常见于任意文件上传、"
                f"命令执行等，建议升级补丁并做终端排查。"
            )
        )


def build_mock_tools() -> list[Tool]:
    return [
        MockAssetQuery(),
        MockAlertQuery(),
        MockVulnQuery(),
        MockSecGPTAnalysis(),
        MockAttackDetect(),
        MockVulnIntelligence(),
    ]
