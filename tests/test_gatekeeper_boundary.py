# -*- coding: utf-8 -*-
"""WebShell 门禁边界回归测试（确定性规则，不使用 LLM、不访问网络）。

负责人/执行人：陈敏
日期：2026-09-13

目的：验证已冻结的门禁在“容易误判”的输入下仍然正确，而不是再开发一套新门禁。
所有用例都是人工构造的确定性输入，不依赖 case1-10 编号，也不反向补入知识库证据。

覆盖的七类边界（与统一合同 v1.1 的门禁边界一一对应）：

1. 否定语义（BOUNDARY-NEG-*）：出现关键词但语义被否定时不得升级。
2. 单一通用进程（BOUNDARY-PROC-*）：cmd.exe / powershell.exe / java.exe 等普通进程不能直接判为 WebShell。
3. 普通反序列化（BOUNDARY-DESER-*）：出现“反序列化”不代表一定发生攻击。
4. 内核驱动（BOUNDARY-KERN-*）：驱动、内核模块、进程隐藏等非 WebShell 证据不得归入 WebShell。
5. 大小写（BOUNDARY-CASE-*）：WebShell / webshell / WEBSHELL 处理必须一致。
6. 空字段（BOUNDARY-EMPTY-*）：summary、event_type、证据摘要为空时安全降级，不得异常放行。
7. 冲突字段（BOUNDARY-CONFLICT-*）：字段互相矛盾时按冻结规则确定性处理，不随机取一个字段。
"""
from __future__ import annotations

import pytest

from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.deep_agent.tools.knowledge import KnowledgeQueryTool
from sec_agent.services.gatekeeper import (
    GateDecision,
    SignalSource,
    SignalStrength,
    WebShellGatekeeper,
)


TEXT_SOURCES = {SignalSource.ALERTS, SignalSource.EVIDENCE}
POSITIVE_STRENGTHS = {SignalStrength.IN_SCOPE_CONFIRMED, SignalStrength.IN_SCOPE_WEAK}


def _event(**overrides: object) -> SecurityEventInput:
    """构造输入事件；未显式覆盖的字段一律留空，空字段本身不产生任何信号。"""
    payload: dict[str, object] = {
        "event_id": "BOUNDARY-000",
        "event_type": "",
        "severity": "",
        "timestamp": "2026-09-13T00:00:00+08:00",
        "source_ip": "192.0.2.10",
        "target_ip": "192.0.2.20",
        "alerts": [],
        "evidence": [],
        "initial_verdict": "",
    }
    payload.update(overrides)
    return SecurityEventInput.from_dict(payload)


def _audit(event_input: SecurityEventInput):
    return WebShellGatekeeper().audit(event_input)


def _strengths(result) -> set:
    return {signal.strength for signal in result.signals}


def _text_signals(result, strengths: set = POSITIVE_STRENGTHS) -> list:
    """返回由 alerts / evidence 文本产生的 WebShell 正向信号。"""
    return [
        signal
        for signal in result.signals
        if signal.source in TEXT_SOURCES and signal.strength in strengths
    ]


class TestNegationSemantics:
    """1. 否定语义：关键词被否定时不得升级为 WebShell 信号。"""

    def test_unreported_webshell_words_do_not_confirm(self) -> None:
        result = _audit(
            _event(
                alerts=["未发现 WebShell 文件落地"],
                evidence=["未检测到 Process.Start 调用", "未观察到 w3wp.exe 派生 shell"],
            )
        )

        assert result.gate_decision != GateDecision.IN_SCOPE
        assert SignalStrength.IN_SCOPE_CONFIRMED not in _strengths(result)
        assert not _text_signals(result), "被否定的关键词不得产生 WebShell 正向文本信号"

    def test_excluded_phrasing_does_not_upgrade(self) -> None:
        result = _audit(
            _event(
                alerts=["已排除 shell.aspx 文件上传"],
                evidence=["可排除 Process.Start 调用", "已排除 WebShell文件落地"],
            )
        )

        assert result.gate_decision != GateDecision.IN_SCOPE
        assert not _text_signals(result), "“排除”语境下的关键词不得升级为 WebShell 信号"

    def test_negation_does_not_leak_across_clauses(self) -> None:
        """否定只作用于同一分句；后半句的确认证据仍必须被识别。"""
        result = _audit(
            _event(
                alerts=["未发现 cmd.exe 子进程，但检测到 w3wp.exe 派生 cmd.exe 命令执行"],
            )
        )

        assert SignalStrength.IN_SCOPE_CONFIRMED in _strengths(result), "同一分句外的确认证据被误吞"

    def test_english_negation_is_respected(self) -> None:
        result = _audit(
            _event(
                evidence=["no evidence of webshell file upload", "not detected: Process.Start"],
            )
        )

        assert not _text_signals(result)


class TestGenericProcessOnly:
    """2. 单一通用进程：普通进程名不得直接判为 WebShell。"""

    def test_generic_process_only_is_not_confirmed(self) -> None:
        result = _audit(
            _event(
                alerts=["检测到子进程 cmd.exe 启动"],
                evidence=["powershell.exe -enc 执行编码命令", "java.exe 进程异常退出"],
            )
        )

        assert SignalStrength.IN_SCOPE_CONFIRMED not in _strengths(result)
        assert result.gate_decision != GateDecision.IN_SCOPE

    def test_generic_process_is_at_most_weak(self) -> None:
        result = _audit(_event(event_type="webshell", evidence=["检测到子进程 cmd.exe 启动"]))

        assert result.gate_decision in {GateDecision.WEAK_SIGNAL, GateDecision.OUT_OF_SCOPE}
        assert _text_signals(result, {SignalStrength.IN_SCOPE_CONFIRMED}) == []
        assert _text_signals(result, {SignalStrength.IN_SCOPE_WEAK}), "通用进程应至少保留弱信号供调查"

    def test_w3wp_alone_is_weak_not_confirmed(self) -> None:
        """IIS 工作进程本身是正常组件，单独出现不能证明 WebShell。"""
        result = _audit(_event(evidence=["检测到 w3wp.exe 工作进程运行"]))

        assert result.gate_decision == GateDecision.WEAK_SIGNAL
        assert SignalStrength.IN_SCOPE_CONFIRMED not in _strengths(result)
        assert _text_signals(result, {SignalStrength.IN_SCOPE_WEAK})

    def test_generic_process_with_webshell_chain_still_confirms(self) -> None:
        """护栏：补上 WebShell 专属证据后仍必须能确认，避免降级过头。"""
        result = _audit(
            _event(
                evidence=[
                    "IIS 工作进程 w3wp.exe 派生 cmd.exe，落地文件内容含 Process.Start 与 "
                    "System.Runtime.InteropServices 调用",
                ],
            )
        )

        assert SignalStrength.IN_SCOPE_CONFIRMED in _strengths(result)
        assert result.gate_decision == GateDecision.IN_SCOPE


class TestPlainDeserialization:
    """3. 普通反序列化：出现“反序列化”不代表一定发生攻击。"""

    def test_plain_deserialization_mention_is_not_attack(self) -> None:
        result = _audit(
            _event(
                evidence=[
                    "代码中存在反序列化调用：BinaryFormatter.Deserialize",
                    "请求体为标准序列化对象",
                ],
            )
        )

        assert SignalStrength.IN_SCOPE_CONFIRMED not in _strengths(result)
        assert result.gate_decision != GateDecision.IN_SCOPE

    def test_deserialization_attack_evidence_still_confirms(self) -> None:
        result = _audit(_event(evidence=["上传的 aspx 文件包含反序列化攻击载荷，由 w3wp.exe 执行"]))

        assert SignalStrength.IN_SCOPE_CONFIRMED in _strengths(result)


class TestKernelAndDriverOutOfScope:
    """4. 内核驱动：驱动、内核模块、进程隐藏等非 WebShell 事件不得被归为 WebShell。"""

    def test_kernel_driver_event_is_not_webshell(self) -> None:
        result = _audit(
            _event(
                event_type="other",
                alerts=["检测到内核驱动文件 Wingtb.sys 加载"],
                evidence=["存在进程隐藏行为，疑似 rootkit"],
            )
        )

        assert not _text_signals(result), "内核驱动证据不得产生 WebShell 范围内信号"
        assert result.gate_decision == GateDecision.OUT_OF_SCOPE, (
            f"内核驱动事件应转交其他攻击链，实际={result.gate_decision}"
        )

    def test_kernel_evidence_mixed_with_webshell_chain_does_not_confirm(self) -> None:
        result = _audit(
            _event(
                evidence=[
                    "检测到内核驱动文件 Wingtb.sys 加载",
                    "同时 w3wp.exe 写入 shell 文件并执行 Process.Start",
                ],
            )
        )

        assert result.overall_strength == SignalStrength.MIXED
        assert result.gate_decision == GateDecision.WEAK_SIGNAL, "确认级与域外证据冲突时不得放行为 in_scope"


class TestCaseInsensitive:
    """5. 大小写：WebShell / webshell / WEBSHELL 处理必须一致。"""

    @pytest.mark.parametrize("event_type", ["WebShell", "webshell", "WEBSHELL"])
    def test_event_type_case_variants_agree(self, event_type: str) -> None:
        result = _audit(_event(event_type=event_type))

        assert result.overall_strength == SignalStrength.IN_SCOPE_WEAK
        assert result.gate_decision == GateDecision.WEAK_SIGNAL

    def test_event_type_dash_and_underscore_variants_agree(self) -> None:
        dash = _audit(_event(event_type="web-shell"))
        underscore = _audit(_event(event_type="web_shell"))

        assert dash.gate_decision == underscore.gate_decision == GateDecision.WEAK_SIGNAL
        assert [s.name for s in dash.signals] == [s.name for s in underscore.signals]

    def test_text_keyword_case_variants_agree(self) -> None:
        upper = _audit(_event(evidence=["W3WP.EXE 派生 CMD.EXE，含 PROCESS.START 调用"]))
        lower = _audit(_event(evidence=["w3wp.exe 派生 cmd.exe，含 Process.Start 调用"]))

        assert upper.gate_decision == lower.gate_decision == GateDecision.IN_SCOPE
        assert [(s.name, s.strength) for s in upper.signals] == [
            (s.name, s.strength) for s in lower.signals
        ]


class TestEmptyFields:
    """6. 空字段：summary / event_type / 证据摘要为空时安全降级，不得异常放行。"""

    def test_all_empty_fields_fail_closed(self) -> None:
        result = _audit(_event())

        assert result.signals == []
        assert result.overall_strength == SignalStrength.INDETERMINATE
        assert result.gate_decision == GateDecision.WEAK_SIGNAL
        assert result.gate_decision != GateDecision.IN_SCOPE

    def test_blank_strings_behave_like_empty(self) -> None:
        blank = _audit(
            _event(
                event_type="   ",
                alerts=["", "   "],
                evidence=["", "\t", None],
                initial_verdict="  ",
            )
        )
        empty = _audit(_event())

        assert blank.gate_decision == empty.gate_decision
        assert blank.overall_strength == empty.overall_strength

    def test_missing_fields_fail_closed(self) -> None:
        result = _audit(SecurityEventInput.from_dict({}))

        assert result.gate_decision != GateDecision.IN_SCOPE
        assert result.gate_decision in set(GateDecision)

    def test_empty_containers_are_reported_as_input_quality_issue(self) -> None:
        result = _audit(_event())

        assert any("信号容器为空" in issue for issue in result.input_quality_issues)

    def test_weak_and_missing_gate_never_release_knowledge(self) -> None:
        """空字段 → weak_signal；weak_signal 与门禁缺失都不得返回确认性知识。"""
        empty_gate = _audit(_event()).gate_decision.value
        weak_result = KnowledgeQueryTool(gate_decision=empty_gate).call({"keyword": "WebShell攻击原理"})
        missing_result = KnowledgeQueryTool().call({"keyword": "WebShell攻击原理"})

        assert empty_gate == GateDecision.WEAK_SIGNAL.value
        assert weak_result.data["knowledge_returned"] is False
        assert missing_result.data["knowledge_returned"] is False
        assert missing_result.error == "missing_knowledge_gate_decision"


class TestConflictingFields:
    """7. 冲突字段：按冻结规则确定性处理，不随机取一个字段。"""

    def test_type_says_webshell_but_evidence_excludes_it(self) -> None:
        event = _event(
            event_type="WebShell",
            evidence=["已排除 WebShell文件上传，落地文件为业务发布包，发布记录一致"],
        )

        first = _audit(event)
        second = _audit(event)

        assert not _text_signals(first), "被排除的证据不得升级为 WebShell 信号"
        assert first.gate_decision == second.gate_decision == GateDecision.WEAK_SIGNAL

    def test_type_says_webshell_but_out_of_scope_evidence_wins(self) -> None:
        result = _audit(
            _event(
                event_type="WebShell",
                alerts=["SSH暴力破解后出现一次 cmd.exe 文本记录"],
                evidence=["SSH 服务日志连续登录失败，判定为身份认证暴力破解"],
                initial_verdict="SSH暴力破解",
            )
        )

        assert result.gate_decision == GateDecision.OUT_OF_SCOPE
        assert any("事件类型与证据冲突" in issue for issue in result.input_quality_issues)

    def test_conflict_resolution_is_order_independent(self) -> None:
        forward = _audit(
            _event(event_type="WebShell", evidence=["SSH 服务日志连续登录失败", "w3wp.exe 写入 shell 文件"])
        )
        backward = _audit(
            _event(event_type="WebShell", evidence=["w3wp.exe 写入 shell 文件", "SSH 服务日志连续登录失败"])
        )

        assert forward.gate_decision == backward.gate_decision
        assert forward.overall_strength == backward.overall_strength
