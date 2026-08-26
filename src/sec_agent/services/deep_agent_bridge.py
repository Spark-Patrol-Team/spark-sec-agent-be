from __future__ import annotations

import importlib
import os
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from sec_agent.domain.models import (
    InvestigationReport,
    InvestigationStep,
    SecurityEvent,
    TriageResult,
    TruthVerdict,
)


class DeepAgentBridgeUnavailable(RuntimeError):
    """deep_agent 子智能体当前不可用。"""


class DeepAgentBridge:
    """将外部 deep_agent 子智能体桥接到当前主链领域模型。"""

    def investigate(self, trace_id: str, run_id: str, event: SecurityEvent, triage: TriageResult) -> InvestigationReport:
        modules = self._load_modules()
        config = modules["load_config"]()
        self._override_config(config)
        llm = modules["LLMClient"](config.llm)
        if not getattr(llm, "available", False):
            raise DeepAgentBridgeUnavailable("deep_agent LLM 未配置")

        tools = self._build_tools(modules, config)
        deep_event = modules["SecurityEventInput"].from_dict(
            self._to_deep_agent_input(trace_id=trace_id, run_id=run_id, event=event, triage=triage)
        )
        deep_report = modules["DeepInvestigationAgent"](config, llm, tools).investigate(deep_event)
        return self._to_domain_report(deep_report, triage)

    def _load_modules(self) -> dict[str, Any]:
        last_error: Exception | None = None
        for package in ("deep_agent", "sec_agent.deep_agent"):
            try:
                return {
                    "package": package,
                    "DeepInvestigationAgent": importlib.import_module(f"{package}.agent").DeepInvestigationAgent,
                    "load_config": importlib.import_module(f"{package}.config").load_config,
                    "LLMClient": importlib.import_module(f"{package}.llm").LLMClient,
                    "SecurityEventInput": importlib.import_module(f"{package}.models").SecurityEventInput,
                    "ToolRegistry": importlib.import_module(f"{package}.tools.base").ToolRegistry,
                    "build_mock_tools": importlib.import_module(f"{package}.tools.mock").build_mock_tools,
                }
            except (ModuleNotFoundError, AttributeError) as exc:
                last_error = exc
                continue
        raise DeepAgentBridgeUnavailable(f"deep_agent 包未安装或接口不符合桥接契约: {last_error}") from last_error

    def _override_config(self, config: Any) -> None:
        tool_mode = os.getenv("DEEP_AGENT_TOOL_MODE")
        if tool_mode and hasattr(config, "tools"):
            config.tools.mode = tool_mode

    def _build_tools(self, modules: dict[str, Any], config: Any) -> Any:
        registry = modules["ToolRegistry"]()
        tool_mode = getattr(getattr(config, "tools", object()), "mode", "auto")
        if tool_mode in {"mock", "auto"}:
            for tool in modules["build_mock_tools"]():
                registry.register(tool)
        # 知识包检索工具（knowledge.query）：本地资源，所有工具模式下都注册
        self._register_knowledge_tools(registry, modules)
        if tool_mode in {"mcp", "auto"}:
            self._register_mcp_tools(registry, config, str(modules["package"]), strict=tool_mode == "mcp")
        return registry

    def _register_knowledge_tools(self, registry: Any, modules: dict[str, Any]) -> None:
        try:
            build_knowledge_tools = importlib.import_module(f"{modules['package']}.tools.knowledge").build_knowledge_tools
        except ModuleNotFoundError:
            return
        for tool in build_knowledge_tools():
            registry.register(tool)

    def _register_mcp_tools(self, registry: Any, config: Any, package: str, strict: bool) -> None:
        try:
            build_mcp_tools = importlib.import_module(f"{package}.tools.mcp_client").build_mcp_tools
        except ModuleNotFoundError as exc:
            if strict:
                raise DeepAgentBridgeUnavailable(f"deep_agent MCP 工具不可用: {exc.name}") from exc
            return
        for tool in build_mcp_tools(config.tools, on_error=lambda message: print(message, file=sys.stderr)):
            registry.register(tool)

    def _to_deep_agent_input(
        self,
        *,
        trace_id: str,
        run_id: str,
        event: SecurityEvent,
        triage: TriageResult,
    ) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": self._event_type(event),
            "severity": triage.priority.value.upper(),
            "timestamp": event.first_seen_at.isoformat(),
            "source_ip": self._first_entity(event, "src_ips"),
            "target_ip": self._first_entity(event, "dst_ips") or self._first_entity(event, "assets"),
            "alerts": list(event.alert_refs),
            "evidence": list(triage.supporting_evidence_refs),
            "initial_verdict": triage.verdict.value,
            "confidence": triage.confidence,
            "triage": triage.model_dump(mode="json"),
            "trace_id": trace_id,
            "run_id": run_id,
        }

    def _to_domain_report(self, deep_report: Any, triage: TriageResult) -> InvestigationReport:
        data = self._as_dict(deep_report)
        steps = [
            InvestigationStep(
                step_no=self._step_no(index, step),
                goal=str(step.get("goal") or step.get("tool") or "deep_agent 调查步骤"),
                observation=str(step.get("new_evidence") or step.get("tool_output") or step),
            )
            for index, step in enumerate(data.get("investigation_steps") or [], start=1)
            if isinstance(step, dict)
        ]
        tool_call_records = data.get("tool_call_records") or []
        return InvestigationReport(
            conclusion=self._conclusion(data.get("verdict") or data.get("conclusion"), triage.verdict),
            final_confidence=self._confidence(data.get("confidence"), triage.confidence),
            timeline=[step.goal for step in steps] or ["deep_agent 子智能体完成深度调查"],
            tool_results=[str(item) for item in tool_call_records],
            key_evidence_refs=[str(item) for item in data.get("key_evidence") or []],
            evidence_relations=[str(data["attack_chain"])] if data.get("attack_chain") else [],
            affected_objects=[str(item) for item in data.get("affected_objects") or []],
            unresolved_questions=[str(item) for item in data.get("unresolved_issues") or []],
            recommended_actions=[str(item) for item in data.get("disposal_suggestions") or []],
            needs_human=bool(data.get("need_manual_takeover")),
            steps=steps,
            summary=str(data.get("conclusion") or "deep_agent 子智能体调查完成"),
        )

    @staticmethod
    def _event_type(event: SecurityEvent) -> str:
        if event.summary:
            return event.summary
        return ",".join(event.alert_refs)

    @staticmethod
    def _first_entity(event: SecurityEvent, key: str) -> str:
        values = event.entities.get(key, [])
        return values[0] if values else ""

    @staticmethod
    def _step_no(index: int, step: dict[str, Any]) -> int:
        value = step.get("step_id")
        return value if isinstance(value, int) and value >= 1 else index

    @staticmethod
    def _conclusion(value: Any, fallback: TruthVerdict) -> TruthVerdict:
        if isinstance(value, TruthVerdict):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            for verdict in TruthVerdict:
                if lowered == verdict.value:
                    return verdict
            if "误报" in value or "良性" in value or "benign" in lowered:
                return TruthVerdict.BENIGN
            if "恶意" in value or "攻击" in value or "malicious" in lowered:
                return TruthVerdict.MALICIOUS
            if "不确定" in value or "人工" in value or "uncertain" in lowered:
                return TruthVerdict.UNCERTAIN
        return fallback

    @staticmethod
    def _confidence(value: Any, fallback: float) -> float:
        if isinstance(value, int | float):
            return min(1.0, max(0.0, float(value)))
        return fallback

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if hasattr(value, "to_dict"):
            data = value.to_dict()
        elif is_dataclass(value):
            data = asdict(value)
        elif isinstance(value, dict):
            data = value
        else:
            raise DeepAgentBridgeUnavailable(f"deep_agent 返回不支持的报告类型: {type(value).__name__}")
        if not isinstance(data, dict):
            raise DeepAgentBridgeUnavailable("deep_agent 报告转换后不是字典")
        return data
