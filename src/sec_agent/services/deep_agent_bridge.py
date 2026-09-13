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

        deep_event = modules["SecurityEventInput"].from_dict(
            self._to_deep_agent_input(trace_id=trace_id, run_id=run_id, event=event, triage=triage)
        )
        gate_decision = self._knowledge_gate_decision(deep_event, config)
        tools = self._build_tools(modules, config, gate_decision=gate_decision)
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

    def _build_tools(
        self,
        modules: dict[str, Any],
        config: Any,
        *,
        gate_decision: str | None,
    ) -> Any:
        registry = modules["ToolRegistry"]()
        tool_mode = getattr(getattr(config, "tools", object()), "mode", "auto")
        knowledge_mode = getattr(
            getattr(config, "tools", object()),
            "knowledge_mode",
            "guarded",
        )

        if tool_mode in {"mock", "auto"}:
            for tool in modules["build_mock_tools"]():
                registry.register(tool)

        # guarded 模式必须先得到有效三档门禁结果。门禁缺失或审计异常时不注册
        # knowledge_query，避免无门禁工具残留形成 fail-open。
        if knowledge_mode == "guarded" and gate_decision in {
            "in_scope",
            "weak_signal",
        }:
            self._register_knowledge_tools(registry, modules, gate_decision)

        if tool_mode in {"mcp", "auto"}:
            self._register_mcp_tools(
                registry,
                config,
                str(modules["package"]),
                strict=tool_mode == "mcp",
            )
        return registry

    def _knowledge_gate_decision(self, deep_event: Any, config: Any) -> str | None:
        knowledge_mode = getattr(
            getattr(config, "tools", object()),
            "knowledge_mode",
            "guarded",
        )
        if knowledge_mode != "guarded":
            return None
        try:
            from sec_agent.services.gatekeeper import WebShellGatekeeper

            decision = WebShellGatekeeper().audit(deep_event).gate_decision.value
        except Exception as exc:  # noqa: BLE001 - 门禁异常必须安全降级为禁用知识
            print(
                f"[warn] 知识门禁审计失败，已禁用知识工具: {type(exc).__name__}",
                file=sys.stderr,
            )
            return None
        return decision if decision in {"in_scope", "weak_signal", "out_of_scope"} else None

    def _register_knowledge_tools(
        self,
        registry: Any,
        modules: dict[str, Any],
        gate_decision: str,
    ) -> None:
        try:
            build_knowledge_tools = importlib.import_module(f"{modules['package']}.tools.knowledge").build_knowledge_tools
        except ModuleNotFoundError:
            return
        for tool in build_knowledge_tools(gate_decision=gate_decision):
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
            "event_type": event.event_type,
            "severity": triage.priority.value.upper(),
            "timestamp": event.first_seen_at.isoformat(),
            "source_ip": self._first_entity(event, "src_ips"),
            "target_ip": self._first_entity(event, "dst_ips") or self._first_entity(event, "assets"),
            "alerts": self._described_refs(event.alert_refs, event.alert_summaries),
            "evidence": self._described_refs(
                triage.supporting_evidence_refs,
                event.evidence_summaries,
            ),
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
    def _described_refs(refs: list[str], descriptions: dict[str, str]) -> list[str]:
        """同时传递稳定引用和语义摘要，供审计定位与门禁判断使用。"""
        return [
            f"{ref}: {descriptions[ref]}" if descriptions.get(ref) else ref
            for ref in refs
        ]

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
