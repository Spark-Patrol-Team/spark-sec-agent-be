from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from sec_agent.api.schemas import EvalComparisonResponse

router = APIRouter(tags=["evaluations"])

FORMAL_COMPARISON_PATH_ENV = "EVAL_COMPARISON_FIXTURE_PATH"
MOCK_SCHEMA_VERSION = "2026-09-07.eval-comparison.v1"
MIN_FORMAL_CASE_COUNT = 6


@router.get(
    "/eval/comparisons",
    response_model=EvalComparisonResponse,
    operation_id="get_eval_comparisons",
    summary="查询 OFF/GUARDED 评测对比数据",
)
def get_eval_comparisons() -> EvalComparisonResponse:
    payload = _load_formal_payload() or _mock_payload()
    return EvalComparisonResponse.model_validate(payload)


def _load_formal_payload() -> dict[str, Any] | None:
    configured_path = os.getenv(FORMAL_COMPARISON_PATH_ENV)
    if not configured_path:
        return None

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包不是合法 JSON: {path}") from exc

    payload = _wrap_payload(raw_payload)
    payload["data_source"] = "formal_fixture"
    return _normalize_payload(payload, min_case_count=MIN_FORMAL_CASE_COUNT)


def _wrap_payload(raw_payload: Any) -> dict[str, Any]:
    if isinstance(raw_payload, list):
        return {
            "schema_version": MOCK_SCHEMA_VERSION,
            "comparison_id": "cmp-formal-import",
            "generated_at": "",
            "data_source": "formal_fixture",
            "suite": {
                "name": "scenario-knowledge-ab",
                "case_count": len(raw_payload),
                "baseline": "OFF",
                "candidate": "GUARDED",
                "knowledge_base": "src/sec_agent/deep_agent/knowledge/webshell-knowledge.md",
            },
            "results": raw_payload,
        }
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=500, detail="正式评测结果包顶层必须是对象或数组")
    if "results" not in raw_payload and isinstance(raw_payload.get("comparisons"), list):
        raw_payload = {**raw_payload, "results": raw_payload["comparisons"]}
    return raw_payload


def _mock_payload() -> dict[str, Any]:
    return _normalize_payload(
        {
            "schema_version": MOCK_SCHEMA_VERSION,
            "comparison_id": "cmp-20260907-mock",
            "generated_at": "2026-09-07T00:00:00+08:00",
            "data_source": "mock_fixture",
            "suite": {
                "name": "scenario-knowledge-ab",
                "case_count": 3,
                "baseline": "OFF",
                "candidate": "GUARDED",
                "knowledge_base": "src/sec_agent/deep_agent/knowledge/webshell-knowledge.md",
            },
            "results": [
                {
                    "case_id": "case1",
                    "knowledge_mode": "knowledge_required",
                    "applicability": "applicable",
                    "off": {
                        "verdict": "malicious",
                        "confidence": 0.72,
                        "matched_knowledge_ids": [],
                        "tool_status": {
                            "knowledge_query": "not_called",
                            "mcp_tools": "skipped",
                            "notes": "OFF 组不启用知识工具。",
                        },
                        "evidence_refs": ["case1:alert"],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": False,
                        "step_count": 2,
                        "duration_ms": 900,
                    },
                    "guarded": {
                        "verdict": "malicious",
                        "confidence": 0.91,
                        "matched_knowledge_ids": [
                            "K-WEBSHELL-PRINCIPLE",
                            "K-WEBSHELL-EVIDENCE-CHECKLIST",
                        ],
                        "tool_status": {
                            "knowledge_query": "success",
                            "mcp_tools": "skipped",
                            "notes": "GUARDED 组命中知识并补充证据引用。",
                        },
                        "evidence_refs": [
                            "case1:alert",
                            "tool:knowledge_query:case1",
                            "knowledge:K-WEBSHELL-PRINCIPLE",
                            "knowledge:K-WEBSHELL-EVIDENCE-CHECKLIST",
                        ],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": False,
                        "step_count": 3,
                        "duration_ms": 1200,
                    },
                    "comparison": {
                        "winner": "GUARDED",
                        "confidence_delta": 0.19,
                        "step_delta": 1,
                        "duration_delta_ms": 300,
                        "reason": "GUARDED 组补充知识证据后置信度提升，未触发禁止结论。",
                    },
                    "human_review": {
                        "status": "pending",
                        "reviewer": None,
                        "reviewed_at": None,
                        "comments": "",
                        "action_items": [],
                    },
                },
                {
                    "case_id": "case5",
                    "knowledge_mode": "knowledge_optional",
                    "applicability": "partially_applicable",
                    "off": {
                        "verdict": "uncertain",
                        "confidence": 0.44,
                        "matched_knowledge_ids": [],
                        "tool_status": {
                            "knowledge_query": "not_called",
                            "mcp_tools": "failed",
                            "notes": "模拟工具失败，OFF 组证据不足。",
                        },
                        "evidence_refs": ["case5:simulated-tool-failure", "tool:mcp:case5"],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": True,
                        "step_count": 3,
                        "duration_ms": 1450,
                    },
                    "guarded": {
                        "verdict": "uncertain",
                        "confidence": 0.58,
                        "matched_knowledge_ids": ["K-WEBSHELL-MANUAL-TAKEOVER"],
                        "tool_status": {
                            "knowledge_query": "success",
                            "mcp_tools": "failed",
                            "notes": "GUARDED 组引用人工接管规则，不编造工具结果。",
                        },
                        "evidence_refs": [
                            "case5:simulated-tool-failure",
                            "tool:mcp:case5",
                            "tool:knowledge_query:case5",
                            "knowledge:K-WEBSHELL-MANUAL-TAKEOVER",
                        ],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": True,
                        "step_count": 4,
                        "duration_ms": 1600,
                    },
                    "comparison": {
                        "winner": "GUARDED",
                        "confidence_delta": 0.14,
                        "step_delta": 1,
                        "duration_delta_ms": 150,
                        "reason": "GUARDED 组在工具失败时保持人工接管，说明证据缺口更完整。",
                    },
                    "human_review": {
                        "status": "pending",
                        "reviewer": None,
                        "reviewed_at": None,
                        "comments": "",
                        "action_items": ["复核报告是否明确区分模拟工具失败与真实平台失败。"],
                    },
                },
                {
                    "case_id": "case6",
                    "knowledge_mode": "knowledge_forbidden",
                    "applicability": "not_applicable",
                    "off": {
                        "verdict": "benign",
                        "confidence": 0.67,
                        "matched_knowledge_ids": [],
                        "tool_status": {
                            "knowledge_query": "not_called",
                            "mcp_tools": "skipped",
                            "notes": "纯非 WebShell 负向对照。",
                        },
                        "evidence_refs": ["case6:negative-control"],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": False,
                        "step_count": 2,
                        "duration_ms": 900,
                    },
                    "guarded": {
                        "verdict": "benign",
                        "confidence": 0.67,
                        "matched_knowledge_ids": [],
                        "tool_status": {
                            "knowledge_query": "not_called",
                            "mcp_tools": "skipped",
                            "notes": "GUARDED 组未调用 WebShell 专属知识。",
                        },
                        "evidence_refs": ["case6:negative-control"],
                        "forbidden_conclusion_hit": False,
                        "manual_takeover": False,
                        "step_count": 2,
                        "duration_ms": 900,
                    },
                    "comparison": {
                        "winner": "TIE",
                        "confidence_delta": 0.0,
                        "step_delta": 0,
                        "duration_delta_ms": 0,
                        "reason": "负向对照中两组均未命中禁止结论，GUARDED 未错误套用知识。",
                    },
                    "human_review": {
                        "status": "pending",
                        "reviewer": None,
                        "reviewed_at": None,
                        "comments": "",
                        "action_items": ["人工复核最终报告是否没有补写 WebShell 事实。"],
                    },
                },
            ],
        }
    )


def _normalize_payload(payload: dict[str, Any], min_case_count: int = 0) -> dict[str, Any]:
    results = list(payload.get("results") or [])
    if len(results) < min_case_count:
        raise HTTPException(status_code=500, detail=f"正式评测结果包至少需要 {min_case_count} 案，当前 {len(results)} 案")

    normalized_results = [_normalize_case_result(result) for result in results]
    suite = dict(payload.get("suite") or {})
    suite["case_count"] = len(normalized_results)
    suite.setdefault("name", "scenario-knowledge-ab")
    suite.setdefault("baseline", "OFF")
    suite.setdefault("candidate", "GUARDED")
    suite.setdefault("knowledge_base", "src/sec_agent/deep_agent/knowledge/webshell-knowledge.md")

    return {
        "schema_version": payload.get("schema_version") or MOCK_SCHEMA_VERSION,
        "comparison_id": payload.get("comparison_id") or "cmp-formal-import",
        "generated_at": payload.get("generated_at") or "",
        "data_source": payload.get("data_source") or "mock_fixture",
        "suite": suite,
        "summary": _build_summary(normalized_results),
        "results": normalized_results,
    }


def _normalize_case_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    normalized["off"] = _normalize_run_result(normalized["off"])
    normalized["guarded"] = _normalize_run_result(normalized["guarded"])
    normalized["comparison"] = _normalize_comparison(normalized)
    return normalized


def _normalize_run_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    breakdown = normalized.get("evidence_breakdown")
    if not isinstance(breakdown, dict):
        breakdown = _build_evidence_breakdown(
            normalized.get("evidence_refs") or [],
            normalized.get("matched_knowledge_ids") or [],
        )
    else:
        breakdown = {
            "event_evidence_refs": _unique_strings(breakdown.get("event_evidence_refs") or []),
            "tool_result_refs": _unique_strings(breakdown.get("tool_result_refs") or []),
            "knowledge_refs": _unique_strings(breakdown.get("knowledge_refs") or []),
        }
    normalized["evidence_breakdown"] = breakdown
    normalized["evidence_refs"] = _unique_strings(
        [
            *(normalized.get("evidence_refs") or []),
            *breakdown["event_evidence_refs"],
            *breakdown["tool_result_refs"],
            *breakdown["knowledge_refs"],
        ]
    )
    return normalized


def _build_evidence_breakdown(evidence_refs: list[str], matched_knowledge_ids: list[str]) -> dict[str, list[str]]:
    event_refs: list[str] = []
    tool_refs: list[str] = []
    knowledge_refs: list[str] = []
    for ref in _unique_strings(evidence_refs):
        if _is_knowledge_ref(ref):
            knowledge_refs.append(ref)
        elif _is_tool_ref(ref):
            tool_refs.append(ref)
        else:
            event_refs.append(ref)
    for knowledge_id in matched_knowledge_ids:
        knowledge_ref = f"knowledge:{knowledge_id}"
        if knowledge_ref not in knowledge_refs:
            knowledge_refs.append(knowledge_ref)
    return {
        "event_evidence_refs": _unique_strings(event_refs),
        "tool_result_refs": _unique_strings(tool_refs),
        "knowledge_refs": _unique_strings(knowledge_refs),
    }


def _normalize_comparison(result: dict[str, Any]) -> dict[str, Any]:
    comparison = dict(result.get("comparison") or {})
    off = result["off"]
    guarded = result["guarded"]
    confidence_delta = round(float(guarded.get("confidence", 0)) - float(off.get("confidence", 0)), 4)
    step_delta = int(guarded.get("step_count", 0)) - int(off.get("step_count", 0))
    duration_delta_ms = int(guarded.get("duration_ms", 0)) - int(off.get("duration_ms", 0))
    comparison.setdefault("confidence_delta", confidence_delta)
    comparison.setdefault("step_delta", step_delta)
    comparison.setdefault("duration_delta_ms", duration_delta_ms)
    comparison.setdefault("winner", _winner(confidence_delta, guarded, off))
    comparison.setdefault("reason", "根据 OFF/GUARDED 结果自动生成对比摘要。")
    return comparison


def _build_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    winners = [result["comparison"]["winner"] for result in results]
    return {
        "total_cases": len(results),
        "guarded_wins": winners.count("GUARDED"),
        "off_wins": winners.count("OFF"),
        "ties": winners.count("TIE"),
        "regressions": winners.count("OFF"),
        "manual_takeovers": sum(
            1
            for result in results
            if result["off"].get("manual_takeover") or result["guarded"].get("manual_takeover")
        ),
        "forbidden_conclusion_hits": sum(
            1
            for result in results
            if result["off"].get("forbidden_conclusion_hit") or result["guarded"].get("forbidden_conclusion_hit")
        ),
    }


def _winner(confidence_delta: float, guarded: dict[str, Any], off: dict[str, Any]) -> str:
    if guarded.get("forbidden_conclusion_hit") and not off.get("forbidden_conclusion_hit"):
        return "OFF"
    if confidence_delta > 0.01:
        return "GUARDED"
    if confidence_delta < -0.01:
        return "OFF"
    return "TIE"


def _is_knowledge_ref(ref: str) -> bool:
    return ref.startswith("knowledge:") or ref.startswith("K-")


def _is_tool_ref(ref: str) -> bool:
    return ref.startswith(("tool:", "tool_result:", "mcp:"))


def _unique_strings(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
