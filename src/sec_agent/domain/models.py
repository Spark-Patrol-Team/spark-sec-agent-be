from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


SCHEMA_VERSION = "2026-08-21.mvp.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BusinessStatus(StrEnum):
    RECEIVED = "RECEIVED"
    CORRELATING = "CORRELATING"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    DECISION_READY = "DECISION_READY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    FAILED = "FAILED"


class TruthVerdict(StrEnum):
    MALICIOUS = "malicious"
    BENIGN = "benign"
    UNCERTAIN = "uncertain"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ToolRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ToolCallStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"


class ToolErrorType(StrEnum):
    AUTH = "auth"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    UNSUPPORTED_TOOL = "unsupported_tool"
    PLATFORM_ERROR = "platform_error"
    UNKNOWN = "unknown"


class ToolSideEffectType(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    STATE_CHANGE = "state_change"


class ExecutionMode(StrEnum):
    MOCK = "mock"
    REAL = "real"


class VerificationStatus(StrEnum):
    EFFECTIVE = "effective"
    INEFFECTIVE = "ineffective"
    UNKNOWN = "unknown"


class EvidenceRef(BaseModel):
    ref_id: str
    source: str
    kind: str
    summary: str | None = None


class AlertRecord(BaseModel):
    alert_id: str
    source: str
    occurred_at: datetime
    name: str
    alert_type: str
    raw_severity: str
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = None
    dst_port: int | None = None
    assets: list[str] = Field(default_factory=list)
    attack_status: str | None = None
    scenario_fields: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    raw_record_ref: str


class NormalizedAlertRecord(BaseModel):
    """平台工具模块输出的标准化 JSONL 告警记录。"""

    event_id: str = Field(min_length=1)
    event_time: datetime
    source_device_type: Literal["STA", "XDR", "EDR", "OTHER"]
    source_device_name: str | None = None
    event_type: Literal["sql_injection", "webshell", "lateral_movement", "unauthorized_access", "other"]
    rule_or_event_name: str = Field(min_length=1)
    severity: Literal["critical", "high", "medium", "low"]
    source_ip: str | None = None
    source_port: int | None = Field(default=None, ge=0, le=65535)
    destination_ip: str | None = None
    destination_port: int | None = Field(default=None, ge=0, le=65535)
    transport_protocol: str | None = None
    application_protocol: str | None = None
    affected_asset: str | None = None
    evidence_source: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    sample_nature: Literal["platform_derived", "synthetic_regression"]
    status: Literal["new", "triaged", "investigating", "contained", "closed"]
    risk_score_seed: int | None = Field(default=None, ge=0, le=100)
    investigation_hint: str | None = None
    recommended_action: str | None = None

    @field_validator("event_time")
    @classmethod
    def event_time_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("event_time 必须包含时区信息")
        return value


class SecurityEvent(BaseModel):
    event_id: str
    alert_refs: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    entities: dict[str, list[str]] = Field(default_factory=dict)
    correlation_reason: str
    alert_count_before: int
    event_count_after: int
    summary: str


class TriageResult(BaseModel):
    verdict: TruthVerdict
    confidence: float = Field(ge=0, le=1)
    risk_score: int = Field(ge=0, le=100)
    priority: Priority
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    opposing_evidence_refs: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    should_investigate: bool
    summary: str


class ToolRequest(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str
    event_id: str
    stage: BusinessStatus
    tool_name: str
    action_name: str
    params: dict[str, Any]
    param_refs: list[str] = Field(default_factory=list)
    reason: str
    dry_run: bool = True
    idempotency_key: str
    risk_level: ToolRiskLevel
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approval_id: str | None = None
    requested_at: datetime = Field(default_factory=utc_now)
    timeout_seconds: int = Field(default=30, ge=1)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1)
    sensitive_param_keys: list[str] = Field(default_factory=list)

    def audit_params(self) -> dict[str, Any]:
        sensitive_keys = set(self.sensitive_param_keys)
        return {key: "***" if key in sensitive_keys else value for key, value in self.params.items()}


class ToolResult(BaseModel):
    call_id: str
    trace_id: str
    event_id: str
    tool_name: str
    action_name: str
    idempotency_key: str
    status: ToolCallStatus
    summary: str
    raw_result_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    output_preview: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    error_type: ToolErrorType | None = None
    error_message: str | None = None
    platform_status: str | None = None
    external_side_effect: bool = False
    side_effect_type: ToolSideEffectType = ToolSideEffectType.NONE
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1)
    started_at: datetime
    ended_at: datetime
    duration_ms: int


class InvestigationStep(BaseModel):
    step_no: int
    goal: str
    tool_request: ToolRequest | None = None
    tool_result: ToolResult | None = None
    observation: str | None = None


class InvestigationReport(BaseModel):
    conclusion: TruthVerdict
    final_confidence: float = Field(ge=0, le=1)
    timeline: list[str] = Field(default_factory=list)
    tool_results: list[str] = Field(default_factory=list)
    key_evidence_refs: list[str] = Field(default_factory=list)
    evidence_relations: list[str] = Field(default_factory=list)
    affected_objects: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    needs_human: bool = False
    steps: list[InvestigationStep] = Field(default_factory=list)
    summary: str


class ResponsePlan(BaseModel):
    action: str
    target: str
    reason: str
    risk_level: ToolRiskLevel
    approval_required: bool
    rollback_available: bool


class ExecutionResult(BaseModel):
    executed: bool
    status: ToolCallStatus
    mode: ExecutionMode
    platform_status: str
    error: str | None = None
    retry_count: int = 0
    idempotency_key: str


class VerificationResult(BaseModel):
    status: VerificationStatus
    method: str
    evidence_refs: list[str] = Field(default_factory=list)
    adjustment_suggestion: str | None = None
    final_status: BusinessStatus


class ResponseResult(BaseModel):
    plan: ResponsePlan | None = None
    execution: ExecutionResult | None = None
    verification: VerificationResult | None = None


class TimelineEntry(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    status: BusinessStatus
    message: str
    elapsed_ms: int | None = None


class ErrorRecord(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    stage: str
    message: str
    recoverable: bool = True


class EventContext(BaseModel):
    schema_version: str = SCHEMA_VERSION
    trace_id: str
    run_id: str
    event_id: str
    status: BusinessStatus
    source: str
    request: StartRunRequest | None = None
    requested_source: str | None = None
    effective_source: str | None = None
    fallback_source: str | None = None
    alert_refs: list[str] = Field(default_factory=list)
    event_summary: SecurityEvent | None = None
    triage: TriageResult | None = None
    investigation: InvestigationReport | None = None
    response: ResponseResult | None = None
    timeline: list[TimelineEntry] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)


class StartRunRequest(BaseModel):
    source: Literal["fixed_sample", "jsonl_sample", "xdr"] = "fixed_sample"
    sample_id: str | None = None
    xdr_event_id: str | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    approver: str
    reason: str
    idempotency_key: str


class EventListItem(BaseModel):
    event_id: str
    run_id: str
    trace_id: str
    status: BusinessStatus
    status_label: str | None = None
    source: str
    sample_id: str | None = None
    xdr_event_id: str | None = None
    requested_source: str | None = None
    effective_source: str | None = None
    fallback_source: str | None = None
    alert_count: int = 0
    risk_score: int | None = None
    priority: Priority | None = None
    verdict: TruthVerdict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    summary: str | None = None


class EventSourceView(BaseModel):
    requested: str | None = None
    effective: str | None = None
    fallback: str | None = None
    sample_id: str | None = None
    xdr_event_id: str | None = None


class EventOverviewView(BaseModel):
    title: str
    summary: str | None = None
    alert_count: int = 0
    risk_score: int | None = None
    priority: Priority | None = None
    verdict: TruthVerdict | None = None
    confidence: float | None = None
    needs_human: bool = False
    affected_assets: list[str] = Field(default_factory=list)
    source_ips: list[str] = Field(default_factory=list)
    destination_ips: list[str] = Field(default_factory=list)


class EventTimelineView(BaseModel):
    at: datetime
    status: BusinessStatus
    status_label: str
    message: str
    elapsed_ms: int | None = None


class EventErrorView(BaseModel):
    at: datetime
    stage: str
    message: str
    recoverable: bool


class EventInvestigationView(BaseModel):
    conclusion: TruthVerdict | None = None
    final_confidence: float | None = None
    summary: str | None = None
    affected_objects: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    key_evidence_refs: list[str] = Field(default_factory=list)
    tool_result_count: int = 0


class EventResponseView(BaseModel):
    action: str | None = None
    target: str | None = None
    risk_level: ToolRiskLevel | None = None
    approval_required: bool | None = None
    execution_status: ToolCallStatus | None = None
    verification_status: VerificationStatus | None = None
    final_status: BusinessStatus | None = None


class EventDetailView(BaseModel):
    schema_version: str
    event_id: str
    run_id: str
    trace_id: str
    status: BusinessStatus
    status_label: str
    source: EventSourceView
    overview: EventOverviewView
    timeline: list[EventTimelineView] = Field(default_factory=list)
    errors: list[EventErrorView] = Field(default_factory=list)
    investigation: EventInvestigationView | None = None
    response: EventResponseView | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EventStatusUpdate(BaseModel):
    status: BusinessStatus
    message: str | None = None
