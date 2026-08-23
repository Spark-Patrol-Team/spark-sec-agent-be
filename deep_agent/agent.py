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


class DeepInvestigationAgent:
    def __init__(self, config: Config, llm: LLMClient, tools: ToolRegistry):
        self.config = config
        self.llm = llm
        self.tools = tools

    # ------------------------------------------------------------------
    def investigate(self, event: SecurityEventInput) -> InvestigationReport:
        if not self.llm.available:
            raise RuntimeError("LLM 未配置，无法运行深度调查。请设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。")

        messages = self._build_messages(event)
        schemas = self.tools.schemas()
        tool_records: list[dict] = []
        max_calls = self.config.agent.max_tool_calls
        tool_call_count = 0

        while tool_call_count < max_calls:
            assistant = self.llm.chat(messages, tools=schemas or None)
            messages.append(assistant)

            # 无工具调用 → LLM 已给出最终报告
            if not assistant["tool_calls"]:
                return self._parse_report(assistant["content"], event, tool_records)

            for tc in assistant["tool_calls"]:
                if tool_call_count >= max_calls:
                    break
                name = tc["function"]["name"]
                args = self._safe_json_loads(tc["function"]["arguments"])
                result = self.tools.call(name, args)
                tool_records.append({
                    "tool": name,
                    "input": args,
                    "output": result.to_str(),
                    "status": result.status,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.to_str(),
                })
                tool_call_count += 1

        # 达到最大工具调用次数仍未得到报告
        return self._fallback_report(event, tool_records, reason="达到最大工具调用次数，证据仍不足")

    # ------------------------------------------------------------------
    def _build_messages(self, event: SecurityEventInput) -> list[dict]:
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
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    # ------------------------------------------------------------------
    def _parse_report(self, content: str, event: SecurityEventInput, tool_records: list[dict]) -> InvestigationReport:
        try:
            data = self._extract_json(content)
        except Exception as e:  # noqa: BLE001
            return self._fallback_report(event, tool_records, reason=f"报告解析失败：{e}")

        # 用代码采集的真实工具调用记录覆盖，保证可审计
        data["tool_call_records"] = tool_records
        data["event_basic_info"] = data.get("event_basic_info") or {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "timestamp": event.timestamp,
            "source_ip": event.source_ip,
            "target_ip": event.target_ip,
        }
        data["trace_id"] = event.trace_id
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

    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_report(event: SecurityEventInput, tool_records: list[dict], reason: str = "") -> InvestigationReport:
        """LLM 未给出有效报告或调查无法继续时的降级报告（证据不足 → 人工接管）。"""
        return InvestigationReport(
            event_basic_info={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "severity": event.severity,
                "timestamp": event.timestamp,
                "source_ip": event.source_ip,
                "target_ip": event.target_ip,
            },
            conclusion="证据不足，无法得出明确调查结论",
            risk_level=event.severity or "未知",
            attack_type=event.event_type or "未知",
            key_evidence=list(event.evidence),
            evidence_source=["上游风险研判"],
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
