# -*- coding: utf-8 -*-
"""知识包检索工具（对应需求中的 `knowledge.query`）。

把《最小 WebShell 知识包》（docs/modules/scenario-knowledge/webshell-knowledge.md，
沈洪旭维护的权威版）解析为可检索条目，Agent 在调查中通过关键词获取：
攻击原理 / 攻击特征 / 管理工具流量特征 / 证据检查清单 / 处置建议模板 等参考信息，
返回结果带 `evidence_refs`，Agent 可直接填入调查报告的 evidence_source / key_evidence。

知识源说明：本工具统一读取沈洪旭维护的权威知识包
`docs/modules/scenario-knowledge/webshell-knowledge.md`，不维护第二份知识副本，
避免与 PR #8（沈洪旭的知识包交付）建立重复入口。

命名说明：OpenAI 兼容接口强制函数名匹配 `^[a-zA-Z0-9_-]+$`，不允许 "."，
因此工具真实名取 `knowledge_query`（语义上等价于需求中的 `knowledge.query`），
ASCII 名无需内部别名映射，LLM 可见名即 `knowledge_query`。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

# 权威知识包 md：沈洪旭维护，位于项目根 docs/modules/scenario-knowledge/ 下。
# 本文件位于 src/sec_agent/deep_agent/tools/，往上 4 级（parents[4]）即项目根。
_DEFAULT_KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "modules" / "scenario-knowledge" / "webshell-knowledge.md"
)


@dataclass
class KnowledgeEntry:
    """一条可检索的知识包条目。"""

    name: str                    # 条目名（如 攻击原理）
    keywords: list[str]          # 匹配关键词（如 WebShell攻击原理 / 中国菜刀）
    content: str                 # 条目正文（markdown）
    evidence_refs: list[str] = field(default_factory=list)   # 证据引用（可填入调查报告）


# 条目规格：标题锚点 + 关键词 + 证据引用（从知识包各章节的引用来源提炼）
_ENTRY_SPECS: list[dict[str, Any]] = [
    {
        "name": "攻击原理",
        "titles": ["攻击原理"],
        "keywords": ["WebShell攻击原理", "攻击原理", "这是什么攻击", "T1505.003", "网页后门", "攻击概述"],
        "evidence_refs": ["MITRE ATT&CK T1505.003 - Server Software Component: Web Shell"],
    },
    {
        "name": "攻击特征速查表",
        "titles": ["攻击特征速查表"],
        "keywords": ["WebShell攻击特征", "攻击特征", "特征速查", "攻击特征速查表"],
        "evidence_refs": ["MITRE ATT&CK T1505.003", "NSA/CISA 联合报告"],
    },
    {
        "name": "主流管理工具与流量特征",
        "titles": ["主流管理工具与流量特征"],
        "keywords": [
            "流量特征", "中国菜刀", "Chopper", "蚁剑", "AntSword", "冰蝎", "Behinder",
            "哥斯拉", "Godzilla", "C99", "Weevely", "管理工具", "隐蔽通道", "DNS隧道",
        ],
        "evidence_refs": ["MITRE ATT&CK S0020 - China Chopper", "CSDN，Webshell管理工具的流量特征"],
    },
    {
        "name": "证据检查清单",
        "titles": ["证据检查清单"],
        "keywords": ["WebShell证据检查清单", "证据检查清单", "检查清单", "证据检查", "检查项", "检测方法", "检测WebShell", "WebShell检测"],
        "evidence_refs": ["NSA/CISA 联合报告", "CISA Eliminate Web Shells (CM0106)"],
    },
    {
        "name": "处置建议模板",
        "titles": ["处置建议模板"],
        "keywords": ["WebShell处置建议", "处置建议", "处置模板", "消除流程", "处置流程", "如何处置"],
        "evidence_refs": ["CISA Eliminate Web Shells (CM0106) - Eliminating Web Shells 章节"],
    },
    {
        "name": "停止条件与人工接管规则",
        "titles": ["停止条件与人工接管规则"],
        "keywords": ["停止条件", "人工接管", "人工接管规则", "停止调查"],
        "evidence_refs": ["《最小 WebShell 知识包》使用约定"],
    },
]


def _split_sections(text: str) -> dict[str, str]:
    """按 markdown 标题（## / ###）切分正文，返回 {标题全文: 正文}。"""
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        match = re.match(r"^#{1,4}\s+(.*)$", raw_line.strip())
        if match:
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(raw_line)
    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()
    return sections


def load_knowledge_entries(md_path: Path | None = None) -> list[KnowledgeEntry]:
    """解析知识包 md，按标题构建可检索条目。

    标题锚点匹配任一即可（容忍章节序号变化）；某节缺失时该条目 content 为空，
    但仍保留（便于调用方感知知识缺口）。
    """
    path = md_path or _DEFAULT_KNOWLEDGE_PATH
    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)

    entries: list[KnowledgeEntry] = []
    for spec in _ENTRY_SPECS:
        content = ""
        for title in spec["titles"]:
            for section_title, body in sections.items():
                if title in section_title:
                    content = body
                    break
            if content:
                break
        entries.append(KnowledgeEntry(
            name=spec["name"],
            keywords=list(spec["keywords"]),
            content=content,
            evidence_refs=list(spec["evidence_refs"]),
        ))
    return entries


def match_keyword(entries: list[KnowledgeEntry], keyword: str) -> KnowledgeEntry | None:
    """关键词匹配：返回得分最高的条目；无命中返回 None。

    打分规则（从高到低）：
      - 关键词与查询词完全相等：100；
      - 条目关键词是查询词子串：60 + 关键词长度（如 "攻击原理" 命中 "WebShell攻击原理"）；
      - 查询词是条目关键词子串：50 + 查询词长度（如 "处置" 命中 "WebShell处置建议"）。
    """
    query = (keyword or "").strip()
    if not query:
        return None
    best_score = 0
    best_entry: KnowledgeEntry | None = None
    for entry in entries:
        score = 0
        for k in entry.keywords:
            if query == k:
                score = max(score, 100)
            elif k and k in query:
                score = max(score, 60 + len(k))
            elif query in k:
                score = max(score, 50 + len(query))
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry if best_score > 0 else None


class KnowledgeQueryTool(Tool):
    """`knowledge.query` 检索工具：按关键词返回知识包条目 + evidence_refs。"""

    name = "knowledge_query"
    description = (
        "检索内置 WebShell 知识包（等价于 knowledge.query）：按关键词获取攻击原理、"
        "攻击特征速查表、主流管理工具流量特征、证据检查清单或处置建议模板。"
        "返回内容含 evidence_refs（证据引用），可直接填入调查报告的证据来源。"
        "关键词示例：WebShell攻击原理、WebShell处置建议、中国菜刀 流量特征、证据检查清单。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "检索关键词，如 WebShell攻击原理 / WebShell处置建议 / 中国菜刀 流量特征 / 证据检查清单",
            },
        },
        "required": ["keyword"],
    }

    def __init__(self, entries: list[KnowledgeEntry] | None = None):
        self._entries = entries if entries is not None else load_knowledge_entries()

    def call(self, params: dict) -> ToolResult:
        keyword = str(params.get("keyword", ""))
        entry = match_keyword(self._entries, keyword)
        if entry is None:
            return ToolResult(status="failed", summary=f"知识库无匹配条目：{keyword}", error="知识库无匹配")
        return ToolResult(
            status="success",
            summary=f"[知识包·{entry.name}]\n{entry.content}\n证据引用 evidence_refs：{entry.evidence_refs}",
            data={"entry": entry.name, "evidence_refs": entry.evidence_refs},
        )


def build_knowledge_tools(md_path: Path | None = None) -> list[Tool]:
    """构建知识包检索工具（默认读取沈洪旭权威版 webshell-knowledge.md）。"""
    return [KnowledgeQueryTool(load_knowledge_entries(md_path))]
