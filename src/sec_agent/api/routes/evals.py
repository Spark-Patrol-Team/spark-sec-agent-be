from __future__ import annotations

from fastapi import APIRouter

from sec_agent.api.schemas import EvalComparisonResponse

router = APIRouter(tags=["evaluations"])


@router.get(
    "/eval/comparisons",
    response_model=EvalComparisonResponse,
    operation_id="get_eval_comparisons",
    summary="查询 OFF/GUARDED 评测对比数据",
)
def get_eval_comparisons() -> EvalComparisonResponse:
    return EvalComparisonResponse.model_validate(
        {
            "schema_version": "2026-09-07.eval-comparison.v1",
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
            "summary": {
                "total_cases": 3,
                "guarded_wins": 2,
                "off_wins": 0,
                "ties": 1,
                "regressions": 0,
                "manual_takeovers": 1,
                "forbidden_conclusion_hits": 0,
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
                        "evidence_refs": ["case5:simulated-tool-failure"],
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
