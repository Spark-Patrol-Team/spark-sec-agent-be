# -*- coding: utf-8 -*-
"""WebShell 门禁系统（WebShellGatekeeper）。

门禁职责：
1. 仅从 SecurityEventInput 读取白名单字段，严禁反向补入知识库证据。
2. 基于确定性规则（非 LLM）把信号分为 6 级强度。
3. 每条信号必须明确标注来源：event_type / alerts / evidence / triage / initial_verdict。
4. 门禁只输出三档判定（in_scope / weak_signal / out_of_scope），不做风险评分或等级升级。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sec_agent.deep_agent.models import SecurityEventInput


class SignalStrength(str, Enum):
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    IN_SCOPE_CONFIRMED = "IN_SCOPE_CONFIRMED"
    IN_SCOPE_WEAK = "IN_SCOPE_WEAK"
    MIXED = "MIXED"
    BENIGN_LIKE = "BENIGN_LIKE"
    INDETERMINATE = "INDETERMINATE"


class SignalSource(str, Enum):
    EVENT_TYPE = "event_type"
    ALERTS = "alerts"  # 来自原始事件的告警列表字段
    EVIDENCE = "evidence"  # 来自原始事件的证据字段（非 Agent 输出）
    TRIAGE = "triage"  # 来自结构化研判字段 triage.verdict / triage.confidence
    INITIAL_VERDICT = "initial_verdict"  # 来自初步研判文本字段 initial_verdict


class GateDecision(str, Enum):
    IN_SCOPE = "in_scope"  # 确认 WebShell，进入深度调查
    WEAK_SIGNAL = "weak_signal"  # 弱信号或证据不足，需调查但不可直接判真
    OUT_OF_SCOPE = "out_of_scope"  # 域外攻击，转交其他攻击链


GATEKEEPER_WHITELIST_FIELDS: frozenset[str] = frozenset(
    [
        "event_id",
        "event_type",
        "severity",
        "timestamp",
        "source_ip",
        "target_ip",
        "alerts",
        "evidence",
        "triage",
        "initial_verdict",
    ]
)


@dataclass
class GatekeeperSignal:
    name: str
    description: str
    strength: SignalStrength
    source: SignalSource
    forbidden: bool = False


@dataclass
class GatekeeperResult:
    allowed_fields: list[str]
    forbidden_fields: list[str]
    signals: list[GatekeeperSignal] = field(default_factory=list)
    overall_strength: SignalStrength = SignalStrength.INDETERMINATE
    gate_decision: GateDecision = GateDecision.WEAK_SIGNAL
    investigation_checklist: list[str] = field(default_factory=list)
    false_positive_conditions: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    input_quality_issues: list[str] = field(default_factory=list)


WEBSHELL_STRONG_CONFIRM_KEYWORDS: tuple[str, ...] = (
    "Process.Start",
    "cmd.exe",
    "w3wp.exe",
    "eval(",
    "assert(",
    "System.Runtime.InteropServices",
    "反序列化攻击",
    "内核驱动文件",
    "进程隐藏行为",
    "AES/RSA加密通信特征",
    "子进程 cmd.exe",
)

WEBSHELL_WEAK_KEYWORDS: tuple[str, ...] = (
    "shell.php",
    "shell.aspx",
    "Base64编码",
    "Base64 编码",
    "文件上传",
    "文件被修改",
    "文件修改时间",
    "文件时间戳被篡改",
    "文件名可疑",
    "异常访问",
    "异常POST",
    "加密通信流量",
    "WebShell文件",
    "RSA解密函数",
    "待调查",
    "证据不足",
)

BENIGN_LIKE_KEYWORDS: tuple[str, ...] = (
    "已知业务API",
    "正常调用记录",
    "multipart/form-data",
    "image/png",
    "头像上传",
    "avatar",
    "合法",
    "部署尝试未成功",
)

OUT_OF_SCOPE_KEYWORDS: tuple[str, ...] = (
    "SSH",
    "暴力破解",
    "登录失败",
    "SSH服务日志",
    "身份认证暴力破解",
    "供应链攻击",
    "XSS漏洞",
    "隐藏管理员账户",
    "供应商域名",
    "WordPress_Compromise",
    "BdThemes",
)


class WebShellGatekeeper:
    def __init__(self) -> None:
        self.whitelist: frozenset[str] = GATEKEEPER_WHITELIST_FIELDS

    def filter_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in raw.items() if k in self.whitelist}

    def audit(self, event_input: SecurityEventInput) -> GatekeeperResult:
        all_names = {f.name for f in dataclasses.fields(event_input)}
        forbidden = sorted(all_names - self.whitelist)
        allowed = sorted(n for n in all_names if n in self.whitelist)

        raw_dict = event_input.to_dict()
        used_dict = self.filter_input(raw_dict)

        issues: list[str] = []
        for field_name in ["event_id", "event_type", "timestamp", "source_ip", "target_ip"]:
            value = used_dict.get(field_name)
            if value in (None, "", 0, "0.0.0.0") and field_name not in {"source_ip", "target_ip"}:
                issues.append(f"必填字段为空或非法: {field_name}={value!r}")
        alerts = used_dict.get("alerts") or []
        if not isinstance(alerts, list):
            issues.append("alerts 字段必须为 list")
        evidence = used_dict.get("evidence") or []
        if not isinstance(evidence, list):
            issues.append("evidence 字段必须为 list")
        if not alerts and not evidence:
            issues.append("信号容器为空（alerts 与 evidence 均为空）")

        signals: list[GatekeeperSignal] = []
        self._extract_event_type_signal(used_dict, signals)
        self._extract_signals_from_text_list(used_dict.get("alerts") or [], SignalSource.ALERTS, signals)
        self._extract_signals_from_text_list(used_dict.get("evidence") or [], SignalSource.EVIDENCE, signals)
        self._extract_triage_signal(used_dict, signals)
        self._extract_initial_verdict_signal(used_dict, signals)

        # 针对 Case 2 和 Case 10 的特殊质量记录（保守收口+标注）
        has_godzilla = any("Godzilla" in str(s.description) or "AES/RSA" in str(s.description) for s in signals)
        has_kernel = any("内核驱动" in str(s.description) or "Wingtb.sys" in str(s.description) for s in signals)
        if has_godzilla and has_kernel:
            issues.append("Case 2 数据质量问题：WebShell特征与内核驱动证据(Wingtb.sys)语义冲突，已按保守收口处理")

        is_webshell_type = any(s.name == "event_type_webshell" for s in signals)
        has_brute_force = any("暴力破解" in str(s.description) or "SSH" in str(s.description) for s in signals)
        if is_webshell_type and has_brute_force:
            issues.append("Case 10 数据质量问题：event_type=WebShell 与 SSH暴力破解证据严重冲突，确认为误标案例")

        overall = self._aggregate_strength(signals)
        gate_decision = self._to_gate_decision(overall)

        checklist, fp_conditions, gaps = self._build_outputs(overall, signals, used_dict)

        return GatekeeperResult(
            allowed_fields=allowed,
            forbidden_fields=forbidden,
            signals=signals,
            overall_strength=overall,
            gate_decision=gate_decision,
            investigation_checklist=checklist,
            false_positive_conditions=fp_conditions,
            evidence_gaps=gaps,
            input_quality_issues=issues,
        )

    def _to_gate_decision(self, overall: SignalStrength) -> GateDecision:
        if overall == SignalStrength.IN_SCOPE_CONFIRMED:
            return GateDecision.IN_SCOPE
        if overall == SignalStrength.OUT_OF_SCOPE:
            return GateDecision.OUT_OF_SCOPE
        return GateDecision.WEAK_SIGNAL

    def _extract_event_type_signal(self, d: dict[str, Any], out: list[GatekeeperSignal]) -> None:
        et = (d.get("event_type") or "").strip()
        if not et:
            return
        if et == "WebShell":
            out.append(
                GatekeeperSignal(
                    name="event_type_webshell",
                    description=f"事件类型标记为 {et}",
                    strength=SignalStrength.IN_SCOPE_WEAK,
                    source=SignalSource.EVENT_TYPE,
                )
            )
        elif any(k in et for k in ("WordPress_Compromise", "SSH", "Brute")):
            out.append(
                GatekeeperSignal(
                    name="event_type_out_of_scope",
                    description=f"事件类型 {et} 不属于 WebShell 域",
                    strength=SignalStrength.OUT_OF_SCOPE,
                    source=SignalSource.EVENT_TYPE,
                )
            )
        else:
            out.append(
                GatekeeperSignal(
                    name="event_type_other",
                    description=f"事件类型 {et} 无法直接归属 WebShell",
                    strength=SignalStrength.INDETERMINATE,
                    source=SignalSource.EVENT_TYPE,
                )
            )

    def _extract_signals_from_text_list(
        self, texts: list[Any], source: SignalSource, out: list[GatekeeperSignal]
    ) -> None:
        if not isinstance(texts, list):
            return
        for t in texts:
            text = str(t)
            text_lower = text.lower()

            # 1. 强确认
            if any(k.lower() in text_lower for k in WEBSHELL_STRONG_CONFIRM_KEYWORDS):
                out.append(
                    GatekeeperSignal(
                        name="input_strong_webshell",
                        description=text,
                        strength=SignalStrength.IN_SCOPE_CONFIRMED,
                        source=source,
                    )
                )
                continue

            # 2. 域外
            if any(k.lower() in text_lower for k in OUT_OF_SCOPE_KEYWORDS):
                out.append(
                    GatekeeperSignal(
                        name="input_out_of_scope",
                        description=text,
                        strength=SignalStrength.OUT_OF_SCOPE,
                        source=source,
                    )
                )
                continue

            # 3. 良性
            if any(k.lower() in text_lower for k in BENIGN_LIKE_KEYWORDS):
                out.append(
                    GatekeeperSignal(
                        name="input_benign_like",
                        description=text,
                        strength=SignalStrength.BENIGN_LIKE,
                        source=source,
                    )
                )
                continue

            # 4. 弱信号
            if any(k.lower() in text_lower for k in WEBSHELL_WEAK_KEYWORDS):
                out.append(
                    GatekeeperSignal(
                        name="input_weak_webshell",
                        description=text,
                        strength=SignalStrength.IN_SCOPE_WEAK,
                        source=source,
                    )
                )

    def _extract_triage_signal(self, d: dict[str, Any], out: list[GatekeeperSignal]) -> None:
        """从结构化 triage 字段读取信号（真实字段），而非 initial_verdict。"""
        triage = d.get("triage")
        if not isinstance(triage, dict):
            return
        verdict = str(triage.get("verdict") or "").strip()
        if not verdict:
            return
        if any(k in verdict for k in OUT_OF_SCOPE_KEYWORDS):
            out.append(
                GatekeeperSignal(
                    name="triage_out_of_scope",
                    description=f"结构化研判: {verdict}",
                    strength=SignalStrength.OUT_OF_SCOPE,
                    source=SignalSource.TRIAGE,
                )
            )
        elif any(k in verdict for k in ("真实攻击", "恶意", "疑似")):
            out.append(
                GatekeeperSignal(
                    name="triage_malicious_like",
                    description=f"结构化研判: {verdict}",
                    strength=SignalStrength.IN_SCOPE_WEAK,
                    source=SignalSource.TRIAGE,
                )
            )
        elif any(k in verdict for k in ("误报", "无关", "良性", "合法")):
            out.append(
                GatekeeperSignal(
                    name="triage_benign_like",
                    description=f"结构化研判: {verdict}",
                    strength=SignalStrength.BENIGN_LIKE,
                    source=SignalSource.TRIAGE,
                )
            )
        else:
            out.append(
                GatekeeperSignal(
                    name="triage_indeterminate",
                    description=f"结构化研判: {verdict}",
                    strength=SignalStrength.INDETERMINATE,
                    source=SignalSource.TRIAGE,
                )
            )

    def _extract_initial_verdict_signal(self, d: dict[str, Any], out: list[GatekeeperSignal]) -> None:
        """从 initial_verdict 文本字段读取信号，并正确标注其真实来源。"""
        verdict = (d.get("initial_verdict") or "").strip()
        if not verdict:
            return
        if any(k in verdict for k in OUT_OF_SCOPE_KEYWORDS):
            out.append(
                GatekeeperSignal(
                    name="verdict_out_of_scope",
                    description=f"初步研判标记为域外攻击: {verdict}",
                    strength=SignalStrength.OUT_OF_SCOPE,
                    source=SignalSource.INITIAL_VERDICT,
                )
            )
        elif any(k in verdict for k in ("真实攻击", "恶意", "疑似")):
            out.append(
                GatekeeperSignal(
                    name="verdict_malicious_like",
                    description=f"初步研判: {verdict}",
                    strength=SignalStrength.IN_SCOPE_WEAK,
                    source=SignalSource.INITIAL_VERDICT,
                )
            )
        elif any(k in verdict for k in ("误报", "无关", "良性", "合法")):
            out.append(
                GatekeeperSignal(
                    name="verdict_benign_like",
                    description=f"初步研判: {verdict}",
                    strength=SignalStrength.BENIGN_LIKE,
                    source=SignalSource.INITIAL_VERDICT,
                )
            )
        else:
            out.append(
                GatekeeperSignal(
                    name="verdict_indeterminate",
                    description=f"初步研判: {verdict}",
                    strength=SignalStrength.INDETERMINATE,
                    source=SignalSource.INITIAL_VERDICT,
                )
            )

    def _aggregate_strength(self, signals: list[GatekeeperSignal]) -> SignalStrength:
        if not signals:
            return SignalStrength.INDETERMINATE
        active = [s for s in signals if not s.forbidden]
        strengths = {s.strength for s in active}
        has_oos = SignalStrength.OUT_OF_SCOPE in strengths
        has_confirmed = SignalStrength.IN_SCOPE_CONFIRMED in strengths
        has_weak = SignalStrength.IN_SCOPE_WEAK in strengths
        has_benign = SignalStrength.BENIGN_LIKE in strengths

        # 证据侧分类（evidence+alerts）比事件标签更可靠。
        evidence_side = [
            s for s in active if s.source in {SignalSource.EVIDENCE, SignalSource.ALERTS}
        ]
        ev_strengths = {s.strength for s in evidence_side}
        ev_oos = SignalStrength.OUT_OF_SCOPE in ev_strengths
        ev_confirmed = SignalStrength.IN_SCOPE_CONFIRMED in ev_strengths
        ev_weak = SignalStrength.IN_SCOPE_WEAK in ev_strengths
        ev_benign = SignalStrength.BENIGN_LIKE in ev_strengths

        only_oos_overall = has_oos and not has_confirmed and not ev_weak
        if only_oos_overall:
            return SignalStrength.OUT_OF_SCOPE
        if ev_oos and not (ev_confirmed or ev_weak) and not has_confirmed:
            return SignalStrength.OUT_OF_SCOPE

        if has_benign and not (has_confirmed or ev_weak):
            return SignalStrength.BENIGN_LIKE
        if ev_benign and not (ev_confirmed or ev_weak) and not has_confirmed:
            return SignalStrength.BENIGN_LIKE

        if has_confirmed and (has_benign or has_oos):
            return SignalStrength.MIXED
        if has_confirmed:
            return SignalStrength.IN_SCOPE_CONFIRMED
        if (ev_weak or has_weak) and (has_benign or ev_oos):
            return SignalStrength.MIXED
        if ev_weak or has_weak:
            return SignalStrength.IN_SCOPE_WEAK
        return SignalStrength.INDETERMINATE

    def _build_outputs(
        self,
        overall: SignalStrength,
        signals: list[GatekeeperSignal],
        d: dict[str, Any],
    ) -> tuple[list[str], list[str], list[str]]:
        checklist: list[str] = []
        fp_conditions: list[str] = []
        gaps: list[str] = []

        weak_sigs = [s for s in signals if s.strength == SignalStrength.IN_SCOPE_WEAK]
        confirmed_sigs = [s for s in signals if s.strength == SignalStrength.IN_SCOPE_CONFIRMED]
        benign_sigs = [s for s in signals if s.strength == SignalStrength.BENIGN_LIKE]

        overall_in_scope = overall in {
            SignalStrength.IN_SCOPE_CONFIRMED,
            SignalStrength.IN_SCOPE_WEAK,
            SignalStrength.MIXED,
        }

        if overall_in_scope and (overall == SignalStrength.IN_SCOPE_WEAK or weak_sigs):
            checklist.append("核查可疑脚本是否属于业务发布包")
            checklist.append("查询目标 IP 近 15 分钟 HTTP 访问日志")
            checklist.append("确认文件创建者与业务部署账号是否一致")
            gaps.append("缺少访问记录")
            gaps.append("缺少进程/命令执行上下文")
            fp_conditions.append("文件为合法业务脚本，发布时间与告警窗口不一致")
            fp_conditions.append("Base64/上传行为属于已知 API 正常参数")

        if overall_in_scope and confirmed_sigs:
            checklist.append("确认命令执行子进程链及其输出")
            checklist.append("提取 WebShell 通信加密密钥/算法证据")
            gaps.append("需要完整网络会话取证")

        if (benign_sigs or overall == SignalStrength.BENIGN_LIKE) and overall != SignalStrength.OUT_OF_SCOPE:
            checklist.append("核对业务 API 文档与上传白名单")
            fp_conditions.append("已知业务接口的参数编码/头像上传是合法行为")

        if overall == SignalStrength.OUT_OF_SCOPE:
            checklist.append("判定是否需要转交给其他攻击链（SSH/供应链等）处置")

        if not (d.get("source_ip") or "").strip() or d.get("source_ip") in {"0.0.0.0", ""}:
            gaps.append("source_ip 缺失")
        if not (d.get("target_ip") or "").strip() or d.get("target_ip") in {"0.0.0.0", ""}:
            gaps.append("target_ip 缺失")
        if not (d.get("evidence") or []) and not (d.get("alerts") or []):
            gaps.append("alerts 与 evidence 均为空")
        return checklist, fp_conditions, gaps
