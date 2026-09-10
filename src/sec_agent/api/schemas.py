from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str
    storage_backend: str
    platform_backend: str


class MetricsResponse(BaseModel):
    total_events: int
    completed_events: int
    human_required_events: int
    failed_events: int
    note: str


class EvalComparisonSuite(BaseModel):
    name: str
    case_count: int
    baseline: Literal["OFF"]
    candidate: Literal["GUARDED"]
    knowledge_base: str


class EvalComparisonSummary(BaseModel):
    total_cases: int
    guarded_wins: int
    off_wins: int
    ties: int
    regressions: int
    manual_takeovers: int
    forbidden_conclusion_hits: int


class EvalToolStatus(BaseModel):
    knowledge_query: Literal["success", "failed", "partial", "not_called", "skipped"]
    mcp_tools: Literal["success", "failed", "partial", "not_called", "skipped"]
    notes: str = ""


class EvalEvidenceBreakdown(BaseModel):
    event_evidence_refs: list[str] = Field(default_factory=list)
    tool_result_refs: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)


class EvalRunResult(BaseModel):
    verdict: Literal["malicious", "benign", "uncertain"]
    confidence: float
    matched_knowledge_ids: list[str]
    tool_status: EvalToolStatus
    evidence_refs: list[str]
    evidence_breakdown: EvalEvidenceBreakdown = Field(default_factory=EvalEvidenceBreakdown)
    forbidden_conclusion_hit: bool
    manual_takeover: bool
    step_count: int
    duration_ms: int


class EvalCaseDelta(BaseModel):
    winner: Literal["OFF", "GUARDED", "TIE"]
    confidence_delta: float
    step_delta: int
    duration_delta_ms: int
    reason: str


class EvalHumanReview(BaseModel):
    status: Literal["pending", "passed", "failed", "needs_follow_up"]
    reviewer: str | None = None
    reviewed_at: str | None = None
    comments: str = ""
    action_items: list[str]


class EvalCaseComparison(BaseModel):
    case_id: str
    knowledge_mode: Literal[
        "knowledge_required",
        "knowledge_optional",
        "knowledge_forbidden",
        "knowledge_not_applicable",
    ]
    applicability: Literal["applicable", "partially_applicable", "not_applicable", "unknown"]
    off: EvalRunResult
    guarded: EvalRunResult
    comparison: EvalCaseDelta
    human_review: EvalHumanReview


class EvalComparisonResponse(BaseModel):
    schema_version: str
    comparison_id: str
    generated_at: str
    data_source: Literal["mock_fixture", "formal_fixture"]
    suite: EvalComparisonSuite
    summary: EvalComparisonSummary
    results: list[EvalCaseComparison]
