from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

from sec_agent.deep_agent.models import SecurityEventInput


class SignalStrength(StrEnum):
    CONFIRMED_WEBSHELL = "confirmed_webshell"
    WEAK_SIGNAL = "weak_signal"
    NON_WEBSHELL = "non_webshell"
    OUT_OF_SCOPE = "out_of_scope"


class SignalSource(StrEnum):
    EVENT_TYPE = "event_type"
    ALERTS = "alerts"
    EVIDENCE = "evidence"
    TRIAGE = "triage"


@dataclass
class GateSignal:
    name: str
    strength: SignalStrength
    source: SignalSource
    description: str
    raw_value: str = ""


@dataclass
class GateResult:
    event_id: str = ""
    read_fields: list[str] = field(default_factory=list)
    signals: list[GateSignal] = field(default_factory=list)
    signal_summary: str = ""
    forbidden_extractions: list[str] = field(default_factory=list)
    input_issues: list[str] = field(default_factory=list)
    investigation_checklist: list[str] = field(default_factory=list)
    false_positive_conditions: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)

    def confirmed_count(self) -> int:
        return sum(1 for s in self.signals if s.strength == SignalStrength.CONFIRMED_WEBSHELL)

    def weak_count(self) -> int:
        return sum(1 for s in self.signals if s.strength == SignalStrength.WEAK_SIGNAL)

    def non_webshell_count(self) -> int:
        return sum(1 for s in self.signals if s.strength == SignalStrength.NON_WEBSHELL)

    def out_of_scope_count(self) -> int:
        return sum(1 for s in self.signals if s.strength == SignalStrength.OUT_OF_SCOPE)


BASE64_RE = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
SUSPICIOUS_FILENAMES = [
    "shell.php", "shell.jsp", "shell.aspx", "cmd.php", "cmd.jsp", "cmd.aspx",
    "webshell", "backdoor", "ant.php", "ant.jsp", "ant.aspx",
    "chopper", "behinder", "godzilla", "weevely",
]
SUSPICIOUS_EXTENSIONS = [".php", ".jsp", ".jspx", ".asp", ".aspx", ".asa", ".cer", ".cdx"]
DOUBLE_EXTENSIONS = [".jpg.php", ".png.php", ".gif.php", ".jpeg.php", ".pdf.php", ".doc.php", ".txt.php"]
HIGH_RISK_FUNCTIONS = [
    "eval(", "exec(", "system(", "shell_exec(", "passthru(", "popen(", "proc_open(",
    "Process.Start", "Runtime.getRuntime", "Server.CreateObject",
    "@eval", "assert(", "create_function(", "call_user_func(",
]
WEBSHELL_TOOL_TOKENS = [
    "AntSword", "Chopper", "Behinder", "Godzilla", "Weevely",
    "antsword", "chopper", "behinder", "godzilla", "weevely",
    "z0=", "z1=", "z2=",
]
WEB_PROCESS_NAMES = ["w3wp.exe", "apache", "httpd", "nginx", "php-cgi", "php-fpm", "tomcat", "java"]
COMMAND_PROCESS_NAMES = ["cmd.exe", "powershell.exe", "bash", "sh", "zsh", "/bin/sh", "/bin/bash"]
NON_WEBSHELL_EVENT_HINTS = [
    "ssh", "brute force", "暴力破解", "登录失败", "login fail",
    "port scan", "端口扫描", "portscan",
    "dos", "ddos", "拒绝服务",
    "ransomware", "勒索",
    "virus", "木马（非web）",
    "data exfiltration", "数据外传",
    "sql注入", "sqli", "union select", "or 1=1", "sleep(", "@@version",
]
FALSE_POSITIVE_BUSINESS_HINTS = [
    "头像上传", "avatar", "用户上传", "user upload",
    "正常调用记录", "known business", "业务api",
    "验证码", "captcha",
    "图片转码", "base64编码图片", "image/png", "image/jpeg",
    "multipart/form-data",
    "已知业务", "正常业务",
]


class WebShellGatekeeper:
    """WebShell 门禁：从 SecurityEventInput 的 event_type / alerts / evidence / triage 四个字段提取信号。

    硬约束：
    - 只能读取上述四个字段 + severity + target_ip + source_ip 顶层结构字段（alerts/evidence 列表本身）；
    - 不能从知识内容（webshell-knowledge.md）反向补入事件证据；
    - 明确区分 CONFIRMED_WEBSHELL / WEAK_SIGNAL / NON_WEBSHELL / OUT_OF_SCOPE 四档。
    """

    def __init__(self) -> None:
        self._forbidden = [
            "已确认WebShell",
            "已建立持久化",
            "攻击成功",
            "已植入后门",
            "攻击者已取得控制",
        ]

    def inspect(self, event: SecurityEventInput) -> GateResult:
        result = GateResult(event_id=event.event_id)
        read_fields: list[str] = []

        if event.event_type:
            read_fields.append("event_type")
            self._check_event_type(event, result)
        if event.alerts:
            read_fields.append("alerts")
            self._check_alerts(event, result)
        if event.evidence:
            read_fields.append("evidence")
            self._check_evidence(event, result)
        if event.triage:
            read_fields.append("triage")
            self._check_triage(event, result)
        if event.severity:
            read_fields.append("severity")
        if event.target_ip:
            read_fields.append("target_ip")
        if event.source_ip:
            read_fields.append("source_ip")
        if event.initial_verdict:
            read_fields.append("initial_verdict")
        if event.confidence is not None:
            read_fields.append("confidence")

        result.read_fields = sorted(set(read_fields))
        self._validate_forbidden(result)
        self._validate_input_quality(event, result)
        self._build_context_pack(result)
        return result

    # ------------------------------------------------------------------
    # 四个来源字段的检查
    # ------------------------------------------------------------------
    def _check_event_type(self, event: SecurityEventInput, result: GateResult) -> None:
        et = (event.event_type or "").strip().lower()
        if et == "webshell":
            result.signals.append(GateSignal(
                name="event_type_tagged_webshell",
                strength=SignalStrength.WEAK_SIGNAL,
                source=SignalSource.EVENT_TYPE,
                description="事件类型被平台标注为 WebShell，但需结合证据确认，不可仅凭标签下结论",
                raw_value=event.event_type or "",
            ))

    def _check_alerts(self, event: SecurityEventInput, result: GateResult) -> None:
        for a in event.alerts or []:
            low = (a or "").lower()
            # 工具直接命中 -> weak（不是 confirmed，工具名可以被自定义UA绕过）
            for tok in WEBSHELL_TOOL_TOKENS:
                if tok.lower() in low:
                    result.signals.append(GateSignal(
                        name=f"alert_webshell_tool_keyword:{tok}",
                        strength=SignalStrength.WEAK_SIGNAL,
                        source=SignalSource.ALERTS,
                        description=f"告警中出现 WebShell 管理工具关键词 {tok}，需交叉验证通信流量与落地文件",
                        raw_value=a,
                    ))
            if "webshell" in low and "通信" in low:
                result.signals.append(GateSignal(
                    name="alert_webshell_traffic_alert",
                    strength=SignalStrength.WEAK_SIGNAL,
                    source=SignalSource.ALERTS,
                    description="告警为 WebShell 通信行为，需证据中确认 POST 参数、加密流或文件落地",
                    raw_value=a,
                ))
            if "上传" in low and ("可疑" in low or "异常" in low):
                result.signals.append(GateSignal(
                    name="alert_suspicious_file_upload",
                    strength=SignalStrength.WEAK_SIGNAL,
                    source=SignalSource.ALERTS,
                    description="检测到可疑/异常文件上传告警，需确认文件内容与扩展名",
                    raw_value=a,
                ))

    def _check_evidence(self, event: SecurityEventInput, result: GateResult) -> None:
        NEG_TOKENS = ("未检测到", "未出现", "未发现", "无任何", "不存在", "未被访问", "未被执行", "无访问", "无执行", "不支持", "未创建")

        seen_web_spawn = False
        seen_highrisk_code = False
        seen_post_base64 = False
        seen_resp_encoded = False

        for e in event.evidence or []:
            text = e or ""
            low = text.lower()
            is_negative = any(tok in text for tok in NEG_TOKENS)

            web_proc_spawn = (not is_negative) and any(w in low for w in WEB_PROCESS_NAMES) and any(c in low for c in COMMAND_PROCESS_NAMES)
            high_risk_code = (not is_negative) and any(f.lower() in low for f in HIGH_RISK_FUNCTIONS)
            if web_proc_spawn:
                seen_web_spawn = True
            if high_risk_code:
                seen_highrisk_code = True

            post_base64 = (not is_negative) and ("post" in low and bool(BASE64_RE.search(text)))
            resp_encoded = (not is_negative) and (("响应体" in text or "response" in low) and ("编码" in text or "base64" in low) and ("系统信息" in text or "whoami" in low))
            if post_base64:
                seen_post_base64 = True
            if resp_encoded:
                seen_resp_encoded = True

            # 单条证据内组合（已不再是唯一方式，兜底保留）
            if web_proc_spawn and high_risk_code:
                result.signals.append(GateSignal(
                    name="evidence_web_process_spawns_shell_plus_highrisk_code",
                    strength=SignalStrength.CONFIRMED_WEBSHELL,
                    source=SignalSource.EVIDENCE,
                    description="Web工作进程创建 cmd/bash 子进程，同时相关文件内容含高危执行函数，满足 WebShell 强证据组合",
                    raw_value=text,
                ))
            elif web_proc_spawn:
                result.signals.append(GateSignal(
                    name="evidence_web_process_spawns_shell",
                    strength=SignalStrength.WEAK_SIGNAL,
                    source=SignalSource.EVIDENCE,
                    description="Web工作进程创建命令行子进程，疑似动态执行，需核实文件/参数来源",
                    raw_value=text,
                ))

            if post_base64 and resp_encoded:
                result.signals.append(GateSignal(
                    name="evidence_post_base64_and_encoded_response_echo",
                    strength=SignalStrength.CONFIRMED_WEBSHELL,
                    source=SignalSource.EVIDENCE,
                    description="异常 POST 请求携带长 Base64 参数，且响应体返回编码后的系统信息/whoami，满足 WebShell 通信强证据",
                    raw_value=text,
                ))

            if high_risk_code and not web_proc_spawn:
                result.signals.append(GateSignal(
                    name="evidence_highrisk_code_pattern",
                    strength=SignalStrength.WEAK_SIGNAL,
                    source=SignalSource.EVIDENCE,
                    description="文件内容/请求体出现高危执行函数，必须结合执行行为或访问链条才可信",
                    raw_value=text,
                ))

            if not is_negative:
                for name in SUSPICIOUS_FILENAMES:
                    if name in low:
                        result.signals.append(GateSignal(
                            name=f"evidence_suspicious_filename:{name}",
                            strength=SignalStrength.WEAK_SIGNAL,
                            source=SignalSource.EVIDENCE,
                            description=f"发现可疑脚本文件名 {name}，需同时存在访问记录或执行行为才可升级",
                            raw_value=text,
                        ))
                        break

                for de in DOUBLE_EXTENSIONS:
                    if de in low:
                        result.signals.append(GateSignal(
                            name=f"evidence_double_extension:{de}",
                            strength=SignalStrength.WEAK_SIGNAL,
                            source=SignalSource.EVIDENCE,
                            description=f"发现双扩展名文件 {de}，常见于伪装上传的 WebShell",
                            raw_value=text,
                        ))
                        break

                if BASE64_RE.search(text) and not post_base64:
                    result.signals.append(GateSignal(
                        name="evidence_base64_long_token",
                        strength=SignalStrength.WEAK_SIGNAL,
                        source=SignalSource.EVIDENCE,
                        description="证据中出现长 Base64 串，可能是编码 payload 或正常业务数据，需区分场景",
                        raw_value=text,
                    ))

                if ("上传" in text or "upload" in low) and not any(b in low for b in FALSE_POSITIVE_BUSINESS_HINTS):
                    result.signals.append(GateSignal(
                        name="evidence_file_upload_without_business_context",
                        strength=SignalStrength.WEAK_SIGNAL,
                        source=SignalSource.EVIDENCE,
                        description="存在文件上传行为但缺少业务上下文说明，需结合路径/扩展名/内容二次判断",
                        raw_value=text,
                    ))

                for tok in WEBSHELL_TOOL_TOKENS:
                    if tok.lower() in low:
                        result.signals.append(GateSignal(
                            name=f"evidence_webshell_tool_marker:{tok}",
                            strength=SignalStrength.WEAK_SIGNAL,
                            source=SignalSource.EVIDENCE,
                            description=f"出现 WebShell 工具特征 {tok}，需结合通信流量与落地文件交叉验证",
                            raw_value=text,
                        ))

            for bf in FALSE_POSITIVE_BUSINESS_HINTS:
                if bf in low:
                    result.signals.append(GateSignal(
                        name=f"evidence_business_context:{bf}",
                        strength=SignalStrength.NON_WEBSHELL,
                        source=SignalSource.EVIDENCE,
                        description=f"出现合法业务上下文标识 {bf}，支持误报判断但需完整业务链路验证",
                        raw_value=text,
                    ))
                    break

            for nh in NON_WEBSHELL_EVENT_HINTS:
                if nh in low:
                    result.signals.append(GateSignal(
                        name=f"evidence_non_webshell_domain:{nh}",
                        strength=SignalStrength.OUT_OF_SCOPE,
                        source=SignalSource.EVIDENCE,
                        description=f"证据指向非 WebShell 攻击域（{nh}），WebShell 知识库应拒绝或不纳入正向证据",
                        raw_value=text,
                    ))
                    break

            if is_negative and ("http请求记录" in low or "该文件被访问" in low or "该文件被执行" in low):
                result.signals.append(GateSignal(
                    name="evidence_no_access_record_for_suspect",
                    strength=SignalStrength.NON_WEBSHELL,
                    source=SignalSource.EVIDENCE,
                    description="可疑对象缺少访问/执行记录，弱化为非 WebShell 辅助信号",
                    raw_value=text,
                ))

        # 跨证据组合 CONFIRMED（文件内容高危 + Web进程spawn子进程，允许来自不同证据）
        if (seen_highrisk_code and seen_web_spawn) and not any(
            s.strength == SignalStrength.CONFIRMED_WEBSHELL and "web_process_spawns_shell_plus_highrisk_code" in s.name
            for s in result.signals
        ):
            result.signals.append(GateSignal(
                name="evidence_combined_highrisk_code_and_web_spawn",
                strength=SignalStrength.CONFIRMED_WEBSHELL,
                source=SignalSource.EVIDENCE,
                description="跨证据组合命中：证据集同时存在高危执行代码和Web进程创建命令行子进程记录，满足 WebShell 强证据组合",
                raw_value="combined:evidence_set",
            ))

        # 跨证据组合 CONFIRMED（POST Base64 + 响应编码系统信息回显）
        if (seen_post_base64 and seen_resp_encoded) and not any(
            s.strength == SignalStrength.CONFIRMED_WEBSHELL and "post_base64_and_encoded_response_echo" in s.name
            for s in result.signals
        ):
            result.signals.append(GateSignal(
                name="evidence_combined_post_base64_and_response_echo",
                strength=SignalStrength.CONFIRMED_WEBSHELL,
                source=SignalSource.EVIDENCE,
                description="跨证据组合命中：证据集同时存在异常 POST Base64 长参数与编码系统信息回显，满足 WebShell 通信强证据",
                raw_value="combined:evidence_set",
            ))

    def _check_triage(self, event: SecurityEventInput, result: GateResult) -> None:
        t = event.triage
        if not isinstance(t, dict):
            return
        verdict = str(t.get("verdict", "")).lower()
        if verdict in ("malicious", "true_positive"):
            result.signals.append(GateSignal(
                name="triage_verdict_malicious",
                strength=SignalStrength.WEAK_SIGNAL,
                source=SignalSource.TRIAGE,
                description="上游分诊给出恶意结论，仅作参考，门禁不得直接作为 confirmed 依据",
                raw_value=verdict,
            ))
        elif verdict in ("benign", "false_positive"):
            result.signals.append(GateSignal(
                name="triage_verdict_benign",
                strength=SignalStrength.NON_WEBSHELL,
                source=SignalSource.TRIAGE,
                description="上游分诊给出良性结论，仅作参考",
                raw_value=verdict,
            ))
        gaps = t.get("evidence_gaps") or []
        for g in gaps:
            if isinstance(g, str) and g:
                result.evidence_gaps.append(g)

    # ------------------------------------------------------------------
    # 输入质量校验 + 上下文包（调查清单 / 误报条件 / 证据缺口）
    # ------------------------------------------------------------------
    def _validate_forbidden(self, result: GateResult) -> None:
        joined = " ".join(s.raw_value.lower() for s in result.signals)
        for fb in self._forbidden:
            if fb.lower() in joined:
                result.forbidden_extractions.append(fb)

    def _validate_input_quality(self, event: SecurityEventInput, result: GateResult) -> None:
        if not event.event_id:
            result.input_issues.append("缺少必填字段 event_id")
        if not event.event_type:
            result.input_issues.append("缺少必填字段 event_type")
        if event.severity and event.severity.upper() not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            result.input_issues.append(f"severity 枚举值异常: {event.severity}")
        if isinstance(event.confidence, (int, float)):
            if not 0.0 <= float(event.confidence) <= 1.0:
                result.input_issues.append(f"confidence 超出 0~1 范围: {event.confidence}")
        # 反向矛盾：evidence 说“完全无关 SSH”，event_type 却是 WebShell，不算错误，但需在 issue 提示
        ssh = any(("ssh" in (e or "").lower() and ("登录" in (e or "") or "暴力" in (e or "") or "login fail" in (e or "").lower())) for e in (event.evidence or []))
        if ssh and (event.event_type or "").lower() == "webshell":
            result.input_issues.append("event_type=WebShell 但证据主体为 SSH 暴力破解，需确认 event_type 标注是否为测试 out_of_scope 用")
        if (event.initial_verdict or "").strip() in ("真实攻击", "攻击成功"):
            result.input_issues.append("initial_verdict 中出现最终结论性词语，应改为中性描述如“待调查/疑似”以避免引导门禁直接接受结论")
        if event.target_ip and event.source_ip and event.target_ip == event.source_ip:
            result.input_issues.append("target_ip 与 source_ip 相同，需核实是否为回环或数据录入错误")

    def _build_context_pack(self, result: GateResult) -> None:
        confirmed = [s for s in result.signals if s.strength == SignalStrength.CONFIRMED_WEBSHELL]
        weak = [s for s in result.signals if s.strength == SignalStrength.WEAK_SIGNAL]
        non_ws = [s for s in result.signals if s.strength == SignalStrength.NON_WEBSHELL]
        oos = [s for s in result.signals if s.strength == SignalStrength.OUT_OF_SCOPE]

        if oos:
            result.signal_summary = "OUT_OF_SCOPE：主体证据为非 WebShell 域，WebShell 知识库拒绝"
        elif confirmed:
            result.signal_summary = f"IN_SCOPE_CONFIRMED：{len(confirmed)} 条强组合证据命中，{len(weak)} 条弱信号辅助"
        elif weak and not non_ws:
            result.signal_summary = f"IN_SCOPE_WEAK：仅 {len(weak)} 条弱信号，需进入调查阶段补齐证据"
        elif non_ws and not weak:
            result.signal_summary = f"BENIGN_LIKE：{len(non_ws)} 条合法业务/否定信号支持误报"
        elif weak and non_ws:
            result.signal_summary = f"MIXED：{len(weak)} 条弱信号 vs {len(non_ws)} 条合法信号，需调查区分"
        else:
            result.signal_summary = "INDETERMINATE：无任何 WebShell 相关信号，需人工复核或补充数据"

        # 调查清单
        if weak and not confirmed:
            result.investigation_checklist.append("检查可疑脚本文件的实际内容（是否含 eval/Process.Start 等）")
            result.investigation_checklist.append("拉取 Web 访问日志核对可疑文件/路径在时间窗口内的 POST/GET 记录")
            result.investigation_checklist.append("检查对应 Web 工作进程在时间窗口内的子进程创建记录")
            result.investigation_checklist.append("核对该上传/编码流量是否能匹配到已登记的业务接口文档")
        if oos:
            result.investigation_checklist.append("切换至对应攻击域知识库（SSH暴力、端口扫描等），不使用 WebShell 知识包")

        # 误报条件
        if any("base64" in s.name for s in weak):
            result.false_positive_conditions.append("若 Base64 能解码为正常业务对象（图片/文档/ID token），则为合法编码业务")
        if any("upload" in s.name for s in weak):
            result.false_positive_conditions.append("若上传目录在白名单且上传文件扩展名/大小符合业务规格说明，则为正常上传")
        if any("filename" in s.name for s in weak):
            result.false_positive_conditions.append("若 shell.php 等命名能在代码仓库中找到正常引用且内容无高危函数，则可能为开发/测试遗留")

        # 证据缺口
        if not any("process" in s.name or "spawn" in s.name for s in result.signals):
            result.evidence_gaps.append("缺少 Web 工作进程的子进程/命令执行记录")
        if not any("highrisk" in s.name or "code_pattern" in s.name for s in result.signals):
            result.evidence_gaps.append("缺少可疑脚本文件的内容扫描结果（eval/Process.Start 等高危函数）")
        if not any("response" in s.name or "encoded_response" in s.name for s in result.signals) and not any("non_webshell_domain" in s.name for s in result.signals):
            result.evidence_gaps.append("缺少 HTTP 响应体内容以确认是否存在编码系统信息回显")
