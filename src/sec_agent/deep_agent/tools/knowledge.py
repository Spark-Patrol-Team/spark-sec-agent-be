# -*- coding: utf-8 -*-
"""知识包检索工具（对应需求中的 `knowledge.query`）。

把《最小 WebShell 知识包》（沈洪旭维护的权威版）解析为可检索条目，Agent 在调查中
通过关键词获取：攻击原理 / 攻击特征 / 管理工具流量特征 / 证据检查清单 / 处置建议模板
等参考信息，返回结果带 `evidence_refs`，Agent 可直接填入调查报告的 evidence_source / key_evidence。

知识源说明：本工具统一读取沈洪旭维护的权威知识包（随包分发的 package-data
`sec_agent/deep_agent/knowledge/webshell-knowledge.md`），不维护第二份知识副本，
避免与 PR #8（沈洪旭的知识包交付）建立重复入口。知识文件经
`[tool.setuptools.package-data]` 声明随 wheel/sdist 分发，`pip install` 后仍可读取。

命名说明：OpenAI 兼容接口强制函数名匹配 `^[a-zA-Z0-9_-]+$`，不允许 "."，
因此工具真实名取 `knowledge_query`（语义上等价于需求中的 `knowledge.query`），
ASCII 名无需内部别名映射，LLM 可见名即 `knowledge_query`。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

# 权威知识包 md：沈洪旭维护，作为 package-data 随包分发。
# 用 importlib.resources 从包内读取，不依赖源码树相对路径，pip install 后同样可用。
_KNOWLEDGE_PACKAGE = "sec_agent.deep_agent"
_KNOWLEDGE_RESOURCE = ("knowledge", "webshell-knowledge.md")


def _default_knowledge_text() -> str:
    """从包内读取权威知识包全文（package-data，随 wheel/sdist 分发）。"""
    resource = resources.files(_KNOWLEDGE_PACKAGE)
    for part in _KNOWLEDGE_RESOURCE:
        resource = resource / part
    return resource.read_text(encoding="utf-8")


@dataclass
class KnowledgeEntry:
    """一条可检索的知识包条目。"""

    name: str                    # 条目名（如 攻击原理）
    keywords: list[str]          # 匹配关键词（如 WebShell攻击原理 / 中国菜刀）
    content: str                 # 条目正文（markdown）
    evidence_refs: list[str] = field(default_factory=list)   # 证据引用（可填入调查报告）

@dataclass
class KnowledgeCard:
    """按统一 Schema 解析后的结构化知识卡。"""

    knowledge_id: str
    topic: str
    applicability: list[str]
    required_evidence: list[str]
    investigation_steps: list[str]
    false_positives: list[str]
    prohibited_inference: list[str]
    source_urls: list[str]
    source_levels: list[str]
    related_cases: list[str]

_REQUIRED_CARD_FIELDS = (
    "主题",
    "适用条件",
    "必要证据",
    "调查步骤",
    "常见误报",
    "禁止推断",
    "来源URL",
    "来源等级",
    "关联案例",
)


def parse_knowledge_card(card_text: str) -> KnowledgeCard:
    """解析单张统一 Schema 的知识卡。"""
    id_match = re.search(r"^## 知识ID：(WSK-\d+)\s*$", card_text, re.M)
    if not id_match:
        raise ValueError("knowledge card missing knowledge_id")

    knowledge_id = id_match.group(1)

    sections: dict[str, list[str]] = {}
    current_field: str | None = None

    for raw_line in card_text.splitlines():
        line = raw_line.strip()

        field_match = re.match(r"^- ([^：]+)：\s*(.*)$", line)
        if field_match:
            field_name = field_match.group(1).strip()
            inline_value = field_match.group(2).strip()

            if field_name in _REQUIRED_CARD_FIELDS:
                current_field = field_name
                sections[current_field] = []
                if inline_value:
                    sections[current_field].append(inline_value)
                continue

        if current_field and line:
            item = re.sub(r"^[-\d.\s]+", "", line).strip()
            if item:
                sections[current_field].append(item)

    missing = [
        field_name
        for field_name in _REQUIRED_CARD_FIELDS
        if not sections.get(field_name)
    ]
    if missing:
        raise ValueError(
            f"{knowledge_id} missing required fields: {', '.join(missing)}"
        )

    return KnowledgeCard(
        knowledge_id=knowledge_id,
        topic=sections["主题"][0],
        applicability=sections["适用条件"],
        required_evidence=sections["必要证据"],
        investigation_steps=sections["调查步骤"],
        false_positives=sections["常见误报"],
        prohibited_inference=sections["禁止推断"],
        source_urls=sections["来源URL"],
        source_levels=sections["来源等级"],
        related_cases=sections["关联案例"],
    )

def parse_knowledge_cards(markdown_text: str) -> list[KnowledgeCard]:
    """解析 Markdown 中的全部知识卡，并校验知识 ID 唯一性。"""
    matches = list(
        re.finditer(
            r"^## 知识ID：(WSK-\d+)\s*$",
            markdown_text,
            re.M,
        )
    )

    if not matches:
        raise ValueError("no knowledge cards found")

    cards: list[KnowledgeCard] = []
    seen_ids: set[str] = set()

    for index, match in enumerate(matches):
        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(markdown_text)
        )

        card = parse_knowledge_card(markdown_text[start:end])

        if card.knowledge_id in seen_ids:
            raise ValueError(
                f"duplicate knowledge_id: {card.knowledge_id}"
            )

        seen_ids.add(card.knowledge_id)
        cards.append(card)

    return cards

_KNOWLEDGE_QUERY_ALIASES = {
    "WebShell攻击原理": "WSK-001",
    "攻击原理": "WSK-001",
    "WebShell攻击特征": "WSK-001",
    "证据检查清单": "WSK-010",
    "WebShell证据检查清单": "WSK-010",
    "WebShell处置建议": "WSK-015",
    "处置建议": "WSK-015",
    "处置流程": "WSK-015",
}
def match_knowledge_card(
    cards: list[KnowledgeCard],
    query: str,
) -> KnowledgeCard | None:
    """按知识ID或主题确定性匹配知识卡；无命中时返回 None。"""
    normalized = (query or "").strip()
    if not normalized:
        return None
    alias_id = _KNOWLEDGE_QUERY_ALIASES.get(normalized)
    if alias_id:
        for card in cards:
            if card.knowledge_id == alias_id:
                return card
    # 1. 知识ID精确匹配，优先级最高
    for card in cards:
        if normalized.upper() == card.knowledge_id.upper():
            return card

    # 2. 主题精确匹配
    for card in cards:
        if normalized == card.topic:
            return card

    # 3. 查询词与主题互为子串
    candidates: list[tuple[int, KnowledgeCard]] = []

    for card in cards:
        if normalized in card.topic:
            candidates.append((len(normalized), card))
        elif card.topic in normalized:
            candidates.append((len(card.topic), card))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]
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

    默认从包内 package-data 读取（`_default_knowledge_text`）；传入 `md_path` 时
    改为读取指定文件（供测试或本地覆盖使用）。
    """
    text = md_path.read_text(encoding="utf-8") if md_path else _default_knowledge_text()
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

    def __init__(
            self,
            cards: list[KnowledgeCard] | None = None,
            gate_decision: str | None = None,
    ):
        if cards is not None:
            self._cards = cards
        else:
            self._cards = parse_knowledge_cards(_default_knowledge_text())

        self._gate_decision = gate_decision


    def call(self, params: dict) -> ToolResult:
        keyword = str(params.get("keyword", "")).strip()

        if not keyword:
            return ToolResult(
                status="failed",
                summary="知识查询关键词为空",
                error="empty_knowledge_query",
            )
        if self._gate_decision == "out_of_scope":
            return ToolResult(
                status="failed",
                summary="当前事件不属于 WebShell 知识适用范围",
                error="knowledge_scope_mismatch",
                data={
                    "gate_decision": "out_of_scope",
                    "knowledge_returned": False,
                },
            )

        if self._gate_decision == "weak_signal":
            return ToolResult(
                status="partial",
                summary="当前仅为弱信号，知识内容受限，不得升级为确认性结论",
                data={
                    "gate_decision": "weak_signal",
                    "knowledge_returned": False,
                    "restriction": "confirmatory_knowledge_blocked",
                },
            )

        if self._gate_decision not in {None, "in_scope"}:
            return ToolResult(
                status="failed",
                summary=f"无效的知识门禁状态：{self._gate_decision}",
                error="invalid_knowledge_gate_decision",
            )
        try:
            card = match_knowledge_card(self._cards, keyword)
        except TimeoutError:
            return ToolResult(
                status="failed",
                summary="知识查询超时",
                error="knowledge_timeout",
                retryable=True,
                data={
                    "knowledge_returned": False,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                status="failed",
                summary="知识查询发生内部错误",
                error="knowledge_internal_error",
                retryable=False,
                data={
                    "knowledge_returned": False,
                    "error_type": type(exc).__name__,
                },
            )

        if card is None:
            return ToolResult(
                status="failed",
                summary=f"知识库无匹配条目：{keyword}",
                error="knowledge_not_found",
                retryable=False,
                data={
                    "knowledge_returned": False,
                },
            )

        return ToolResult(
            status="success",
            summary=f"[知识卡·{card.knowledge_id}] {card.topic}",
            data={
                "knowledge_id": card.knowledge_id,
                "topic": card.topic,
                "applicability": card.applicability,
                "required_evidence": card.required_evidence,
                "investigation_steps": card.investigation_steps,
                "false_positives": card.false_positives,
                "prohibited_inference": card.prohibited_inference,
                "source_citations": {
                    "urls": card.source_urls,
                    "levels": card.source_levels,
                },
                "related_cases": card.related_cases,
                "knowledge_returned": True,
                "gate_decision": self._gate_decision or "in_scope",
            },
        )


def build_knowledge_tools(
    md_path: Path | None = None,
    gate_decision: str | None = None,
) -> list[Tool]:
    """构建结构化知识卡检索工具。"""
    text = (
        md_path.read_text(encoding="utf-8")
        if md_path
        else _default_knowledge_text()
    )
    cards = parse_knowledge_cards(text)

    return [
        KnowledgeQueryTool(
            cards,
            gate_decision=gate_decision,
        )
    ]