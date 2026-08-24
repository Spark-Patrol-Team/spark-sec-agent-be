# -*- coding: utf-8 -*-
"""深度调查 Agent 数据模型。

对齐两份文档：
- 《深度调查 agent 设计》：输入 10 字段、输出 12 项报告。
- 《统一接口与数据流（方案校准版）》：SecurityEvent / TriageResult / InvestigationReport 契约。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class SecurityEventInput:
    """深度调查 Agent 的标准化输入事件。

    同时兼容设计文档 10 字段，以及上游 SecurityEvent + TriageResult 的关键字段。
    """
    event_id: str = ""
    event_type: str = ""              # 事件类型，如 WebShell
    severity: str = ""                # 风险等级 HIGH / CRITICAL / MEDIUM / LOW
    timestamp: str = ""               # 事件时间
    source_ip: str = ""               # 攻击源
    target_ip: str = ""               # 目标资产
    alerts: list[str] = field(default_factory=list)      # 已有告警
    evidence: list[str] = field(default_factory=list)    # 已有证据
    initial_verdict: str = ""         # 初步风险研判
    confidence: float = 0.0           # 研判置信度 0~1
    triage: Optional[dict] = None     # 风险研判完整结果（真实性/风险分/优先级/证据缺口等）
    trace_id: str = ""                # 全链路追踪编号
    run_id: str = ""                  # 本次运行编号

    @classmethod
    def from_dict(cls, d: dict) -> "SecurityEventInput":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InvestigationReport:
    """深度调查结构化报告（InvestigationReport 契约）。"""
    event_basic_info: dict = field(default_factory=dict)
    conclusion: str = ""                    # 调查结论
    risk_level: str = ""                    # 风险等级
    attack_type: str = ""                   # 攻击类型
    key_evidence: list[str] = field(default_factory=list)      # 关键证据
    evidence_source: list[str] = field(default_factory=list)   # 证据来源
    investigation_steps: list[dict] = field(default_factory=list)  # 调查步骤
    tool_call_records: list[dict] = field(default_factory=list)    # 工具调用记录
    attack_chain: str = ""                  # 攻击链 / 攻击过程
    confidence: float = 0.0                 # 调查置信度 0~1
    disposal_suggestions: list[str] = field(default_factory=list)  # 处置建议
    need_manual_takeover: bool = False      # 是否需要人工接管
    manual_takeover_reason: str = ""        # 人工接管原因
    unresolved_issues: list[str] = field(default_factory=list)     # 尚未解决的问题
    affected_objects: list[str] = field(default_factory=list)      # 涉及和受影响对象
    trace_id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "InvestigationReport":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)
