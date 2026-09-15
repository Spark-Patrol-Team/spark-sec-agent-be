# -*- coding: utf-8 -*-
"""深度调查 Agent 核心。

实现设计文档的「调查闭环」：
接收事件 → 分析已有证据 → 识别证据缺口 → 规划调查步骤 → 调用工具补证 →
更新结论与置信度 → 判断停止条件 → 输出结构化调查报告。

采用 LLM 工具调用循环（ReAct 风格），由 LLM 自主决定调用哪些工具、何时停止。
工具调用记录由代码侧真实采集，保证全程可审计、不依赖 LLM 复述。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from .config import Config
from .llm import LLMClient
from .models import SecurityEventInput, InvestigationReport
from .tools.base import ToolRegistry

SYSTEM_PROMPT = """你是「深度调查安全分析 Agent」，运行在深信服 XDR 安全运营平台上。你的职责是：对上游风险研判后标记为高风险、疑似真实攻击或现有证据不足的安全事件，开展自动化深度调查——在已有结论基础上主动补充证据、验证攻击判断，最终输出结构化调查报告。

# 调查闭环
严格按以下闭环执行：接收事件 → 分析已有证据 → 识别证据缺口 → 规划调查步骤 → 调用工具补充证据 → 更新结论与置信度 → 判断停止条件 → 输出结构化报告。不要跳过「识别证据缺口」环节。

# 调查原则
1. 绝不编造证据：所有结论必须基于工具真实返回的数据。工具返回失败/为空时，如实记录"数据不可得"，严禁臆造或填充虚假证据。
2. 缺口驱动：优先补充对"判定是否真实攻击"最关键、最缺失的证据，而非漫无目的地调用工具。
3. 证据充分性优先于数量：少量高质量关键证据优于大量无关数据。
4. 置信度(0~1)随证据增减合理调整，结论变化中说明调整理由。
5. 调查过程与工具真实返回一致，不得在报告中编造工具结果。

# 可用工具
工具清单见系统提供的 tools 定义，你可自主决定调用哪些工具、调用几次（可多轮组合）。
WebShell 类事件典型调查路径：先查目标资产信息，再查相关告警与漏洞，必要时做攻击检测、调用安全GPT研判、查询漏洞情报。

# 收尾原则（重要）
工具调用次数有限，不要为「多查一点」耗尽步数。证据足以支撑结论时，立即停止调用工具，直接输出最终调查报告 JSON；始终为「直接输出报告」保留至少一次收尾（只输出 JSON、不调用工具的轮次）。工具返回为空或失败时，如实记录「数据不可得」，不要反复调用同一工具。

# 停止条件（满足任一即停止调用工具，直接输出报告）
1. 证据充分：已能支撑明确的调查结论；
2. 达到最大调查步数（约 5 步）；
3. 工具无法获得数据：关键查询失败、数据为空或权限不足。

# 人工接管条件（命中任一，need_manual_takeover 置为 true 并说明原因）
1. 高风险事件 + 证据不足 + 关键工具调用失败；
2. 调查结果与输入研判存在明显冲突；
3. 涉及高风险处置动作（阻断、隔离、删除、终止进程等，需人工确认）。

# 输出格式（严格遵守）
当你决定结束调查时，输出一个且仅一个合法的 JSON 对象（不要输出 markdown 代码块围栏或任何额外文字），结构如下：

{
  "event_basic_info": {"event_id":"","event_type":"","severity":"","timestamp":"","source_ip":"","target_ip":""},
  "conclusion": "调查结论",
  "risk_level": "HIGH/MEDIUM/LOW",
  "attack_type": "攻击类型",
  "key_evidence": ["关键证据1"],
  "evidence_source": ["证据来源1"],
  "investigation_steps": [{"step_id":1,"goal":"调查目标","evidence_gap":"证据缺口","tool":"调用工具","tool_input":{},"tool_output":"摘要","new_evidence":"新增证据","conclusion_change":"结论变化"}],
  "attack_chain": "攻击链/攻击过程描述",
  "confidence": 0.88,
  "disposal_suggestions": ["处置建议1"],
  "need_manual_takeover": false,
  "manual_takeover_reason": "",
  "unresolved_issues": ["尚未解决的问题"],
  "affected_objects": ["涉及或受影响的资产/IP"]
}

字段说明：
- confidence：0~1 的小数，表示调查置信度。
- 所有字段都必须填写，无法获得的信息填"未知"或空字符串，不得省略任何字段。"""


_KNOWLEDGE_TOOL_PROMPT = """

# 知识工具边界
需要攻击原理 / 攻击特征 / 证据检查清单 / 处置建议等参考知识时，可调用 knowledge_query（关键词示例：WebShell攻击原理、WebShell证据检查清单、WebShell处置建议）。其 source_citations 仅表示知识卡来源，不是当前事件的观测证据，不得写入报告的 key_evidence 或 evidence_source，也不得据此把攻击判定为已发生。"""


# 接近工具调用上限时注入的收尾提醒（防止 LLM 耗尽步数导致降级）
_WRAPUP_REMINDER = (
    "注意：你已接近工具调用上限（剩余约 {remaining} 次）。"
    "若现有证据足以支撑结论，请立即停止调用工具，直接输出最终调查报告 JSON；"
    "不要为求全继续调用工具。"
)

_FORCED_WRAPUP_PROMPT = (
    "工具调用额度已经用完。现在禁止继续调用任何工具；请仅依据已有事件输入和真实工具返回，"
    "立即输出一个符合既定格式的合法调查报告 JSON，不要输出 markdown 或额外文字。"
)


_OUT_OF_SCOPE_REPORT_CONSTRAINT = """

# 域外事件报告约束（门禁判定 out_of_scope）
本事件不属于当前 WebShell 场景。生成报告时必须遵守：
- attack_chain 不得写入植入、持久化、后门、木马、最终载荷等 WebShell 攻击链特征；
- disposal_suggestions 不得写入清除/排查 WebShell、查杀后门等当前场景专属动作；
- 如实说明当前场景证据不足并建议转交匹配场景，禁止臆造 WebShell 事实。"""

_OUT_OF_SCOPE_ATTACK_CHAIN_TERMS = (
    "植入",
    "持久化",
    "后门",
    "木马",
    "最终载荷",
    "persistence",
    "backdoor",
    "trojan",
    "final payload",
    "webshell payload",
    "web shell payload",
)
_OUT_OF_SCOPE_CONCLUSION_TERMS = (
    "植入",
    "持久化",
    "后门",
    "木马",
    "最终载荷",
    "可致webshell",
    "核查webshell",
    "核查 webshell",
    "排查webshell",
    "排查 webshell",
    "清除webshell",
    "清除 webshell",
    "persistence",
    "backdoor",
    "trojan",
    "final payload",
    "webshell payload",
    "web shell payload",
)
_OUT_OF_SCOPE_DISPOSAL_TERMS = (
    "webshell",
    "web shell",
    "后门",
    "木马",
    "查杀",
    "backdoor",
    "trojan",
)
_OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER = "域外事件，不适用当前场景攻击链；请转交匹配场景继续调查。"
_OUT_OF_SCOPE_CONCLUSION_PLACEHOLDER = (
    "该事件属于非 WebShell 场景，当前知识不适用；现有证据不足，请转交匹配场景继续调查。"
)
_OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER = "建议人工复核并转交匹配场景，不执行当前场景专属处置。"


def _contains_term(text: Any, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in terms)


def sanitize_out_of_scope_report(data: dict[str, Any]) -> dict[str, Any]:
    """确定性清洗域外报告中的当前场景专属攻击链与处置措辞。"""
    cleaned = dict(data)

    if _contains_term(cleaned.get("conclusion"), _OUT_OF_SCOPE_CONCLUSION_TERMS):
        cleaned["conclusion"] = _OUT_OF_SCOPE_CONCLUSION_PLACEHOLDER

    if _contains_term(cleaned.get("attack_chain"), _OUT_OF_SCOPE_ATTACK_CHAIN_TERMS):
        cleaned["attack_chain"] = _OUT_OF_SCOPE_ATTACK_CHAIN_PLACEHOLDER

    suggestions = cleaned.get("disposal_suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [suggestions]
    kept = [
        str(item)
        for item in suggestions
        if not _contains_term(item, _OUT_OF_SCOPE_DISPOSAL_TERMS)
    ]
    cleaned["disposal_suggestions"] = kept or [_OUT_OF_SCOPE_DISPOSAL_PLACEHOLDER]
    return cleaned


class DeepInvestigationAgent:
    def __init__(self, config: Config, llm: LLMClient, tools: ToolRegistry):
        self.config = config
        self.llm = llm
        self.tools = tools

    # ------------------------------------------------------------------
    def investigate(
        self,
        event: SecurityEventInput,
        gate_decision: str | None = None,
    ) -> InvestigationReport:
        if not self.llm.available:
            raise RuntimeError("LLM 未配置，无法运行深度调查。请设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。")

        messages = self._build_messages(event, gate_decision=gate_decision)
        schemas = self.tools.schemas()
        tool_records: list[dict] = []
        max_calls = self.config.agent.max_tool_calls
        tool_call_count = 0
        wrapup_reminded = False

        while tool_call_count < max_calls:
            # 接近上限：注入收尾提醒，避免 LLM 耗尽步数后降级
            remaining = max_calls - tool_call_count
            if remaining <= 2 and not wrapup_reminded:
                messages.append({"role": "system", "content": _WRAPUP_REMINDER.format(remaining=remaining)})
                wrapup_reminded = True

            assistant = self.llm.chat(messages, tools=schemas or None)
            messages.append(assistant)

            # 无工具调用 → LLM 已给出最终报告
            if not assistant["tool_calls"]:
                return self._parse_report(
                    assistant["content"],
                    event,
                    tool_records,
                    gate_decision=gate_decision,
                )

            for tc in assistant["tool_calls"]:
                if tool_call_count >= max_calls:
                    # assistant 可能在同一轮返回多个 tool_calls。即使额度已用完，
                    # 也要逐个补齐 tool 响应，保持下一轮消息满足工具调用协议。
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "[未执行] 已达到工具调用上限；请根据现有证据直接输出最终报告。",
                    })
                    continue
                # LLM 使用的是 ASCII 内部别名，解析回真实工具名执行并留痕
                real_name = self.tools.resolve(tc["function"]["name"])
                args = self._safe_json_loads(tc["function"]["arguments"])
                result = self.tools.call(real_name, args)
                record = {
                    "tool": real_name,
                    "input": args,
                    "output": result.to_str(),
                    "status": result.status,
                }
                # 知识卡来源单独留在工具调用记录中，不能混入当前事件证据。
                if real_name == "knowledge_query" and isinstance(result.data, dict):
                    citations = result.data.get("source_citations")
                    if isinstance(citations, dict):
                        record["knowledge_citations"] = {
                            "urls": list(citations.get("urls") or []),
                            "levels": list(citations.get("levels") or []),
                        }
                tool_records.append(record)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.to_str(),
                })
                tool_call_count += 1

        # 工具额度与最终报告生成分离：额度耗尽后仍保留一次无工具的强制收尾，
        # 避免最后一个（包括知识）工具调用挤掉结构化报告输出。
        messages.append({"role": "system", "content": _FORCED_WRAPUP_PROMPT})
        assistant = self.llm.chat(messages, tools=None)
        if not assistant.get("tool_calls"):
            return self._parse_report(
                assistant.get("content", ""),
                event,
                tool_records,
                gate_decision=gate_decision,
            )

        return self._fallback_report(
            event,
            tool_records,
            reason="达到最大工具调用次数，且强制收尾仍未生成报告",
            gate_decision=gate_decision,
        )

    # ------------------------------------------------------------------
    def _build_messages(
        self,
        event: SecurityEventInput,
        gate_decision: str | None = None,
    ) -> list[dict]:
        payload = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "timestamp": event.timestamp,
            "source_ip": event.source_ip,
            "target_ip": event.target_ip,
            "alerts": event.alerts,
            "evidence": event.evidence,
            "initial_verdict": event.initial_verdict,
            "confidence": event.confidence,
            "triage": event.triage or {},
        }
        user_content = "以下是待调查的安全事件，请开始深度调查：\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        system_content = SYSTEM_PROMPT
        tools = getattr(self, "tools", None)
        if tools is not None and tools.get("knowledge_query") is not None:
            system_content += _KNOWLEDGE_TOOL_PROMPT
        if gate_decision == "out_of_scope":
            system_content += _OUT_OF_SCOPE_REPORT_CONSTRAINT
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    # ------------------------------------------------------------------
    def _parse_report(
        self,
        content: str,
        event: SecurityEventInput,
        tool_records: list[dict],
        gate_decision: str | None = None,
    ) -> InvestigationReport:
        try:
            data = self._extract_json(content)
        except Exception as e:  # noqa: BLE001
            return self._fallback_report(
                event,
                tool_records,
                reason=f"报告解析失败：{e}",
                gate_decision=gate_decision,
            )

        # 没有任何真实成功/部分成功工具记录时，
        # 不允许 LLM 生成未经验证的调查步骤或证据。
        successful_event_records = [
            record
            for record in tool_records
            if record.get("status") in {"success", "partial"}
            and record.get("tool") != "knowledge_query"
        ]

        if not successful_event_records:
            return self._fallback_report(
                event,
                tool_records,
                reason="没有成功返回事件观测的调查工具；知识结果不能单独支撑事件结论",
                gate_decision=gate_decision,
            )
        # investigation_steps 只能引用代码侧真实执行过的工具，防止 LLM 虚构工具调用步骤。
        # LLM 使用 ASCII 别名，tool_records 保存 resolve 后的真实工具名，
        # 因此真实名和别名都加入允许集合。
        executed_tools = set()
        for record in tool_records:
            name = record.get("tool")
            if name:
                executed_tools.add(name)
                executed_tools.add(self.tools.alias_of(name))

        data["investigation_steps"] = [
            step
            for step in (data.get("investigation_steps") or [])
            if isinstance(step, dict)
            and step.get("tool") in executed_tools
        ]

        # 用代码侧真实采集记录覆盖 LLM 输出，保证可审计。
        data["tool_call_records"] = tool_records

        # key_evidence/evidence_source 只由上游事件证据和非知识工具结果生成。
        # 不信任 LLM 对知识来源与当前事件证据的自行分类。
        key_evidence, evidence_source = self._derive_event_evidence(event, tool_records)
        data["key_evidence"] = key_evidence
        data["evidence_source"] = evidence_source

        data["event_basic_info"] = data.get("event_basic_info") or {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "timestamp": event.timestamp,
            "source_ip": event.source_ip,
            "target_ip": event.target_ip,
        }

        data["trace_id"] = event.trace_id
        if gate_decision == "out_of_scope":
            data = sanitize_out_of_scope_report(data)
        return InvestigationReport.from_dict(data)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        # 去掉 markdown 代码块围栏
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # 截取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("报告不是 JSON 对象")
        return data

    @staticmethod
    def _safe_json_loads(s: str) -> dict:
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _derive_event_evidence(
        event: SecurityEventInput,
        tool_records: list[dict],
    ) -> tuple[list[str], list[str]]:
        """从可信运行记录派生事件证据；知识工具只保留在调用审计中。"""

        key_evidence = [str(item) for item in event.evidence if str(item).strip()]
        evidence_source = ["上游风险研判"]
        seen_ev = set(key_evidence)
        seen_src = set(evidence_source)

        for record in tool_records:
            if record.get("status") not in {"success", "partial"}:
                continue
            tool = str(record.get("tool") or "")
            if tool == "knowledge_query":
                continue
            source = f"来源工具: {tool}" if tool else ""
            if source and source not in seen_src:
                seen_src.add(source)
                evidence_source.append(source)
            output = str(record.get("output") or "").strip()[:200]
            if output and output not in seen_ev:
                seen_ev.add(output)
                key_evidence.append(output)

        return key_evidence, evidence_source

    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_report(
        event: SecurityEventInput,
        tool_records: list[dict],
        reason: str = "",
        gate_decision: str | None = None,
    ) -> InvestigationReport:
        """LLM 未给出有效报告或调查无法继续时的降级报告（证据不足 → 人工接管）。

        尽力提炼已采集的事件证据，避免降级报告完全为空：
        - knowledge_query 的 source_citations 只保留在 tool_call_records，绝不进入事件证据；
        - 其他成功工具的调用名 → evidence_source（"来源工具: ..."）；
        - 其他成功工具的返回摘要 → key_evidence（截断 200 字符）。
        """
        key_evidence, evidence_source = DeepInvestigationAgent._derive_event_evidence(
            event,
            tool_records,
        )

        report = InvestigationReport(
            event_basic_info={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "severity": event.severity,
                "timestamp": event.timestamp,
                "source_ip": event.source_ip,
                "target_ip": event.target_ip,
            },
            conclusion="证据不足，无法得出明确调查结论（已采集部分工具证据，详见 key_evidence / evidence_source）",
            risk_level=event.severity or "未知",
            attack_type=event.event_type or "未知",
            key_evidence=key_evidence,
            evidence_source=evidence_source,
            investigation_steps=[],
            tool_call_records=tool_records,
            attack_chain="未知",
            confidence=event.confidence,
            disposal_suggestions=["建议人工介入进一步调查"],
            need_manual_takeover=True,
            manual_takeover_reason=reason or "工具无法获得充分数据，证据不足",
            unresolved_issues=["证据不足"],
            affected_objects=[event.target_ip] if event.target_ip else [],
            trace_id=event.trace_id,
        )
        if gate_decision == "out_of_scope":
            return InvestigationReport.from_dict(
                sanitize_out_of_scope_report(report.to_dict())
            )
        return report
