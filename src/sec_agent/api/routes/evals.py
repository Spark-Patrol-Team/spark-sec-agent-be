from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from sec_agent.api.schemas import EvalComparisonResponse

router = APIRouter(tags=["evaluations"])

FORMAL_COMPARISON_PATH_ENV = "EVAL_COMPARISON_FIXTURE_PATH"
MOCK_SCHEMA_VERSION = "2026-09-07.eval-comparison.v1"
MIN_FORMAL_CASE_COUNT = 6
ACTUAL_COMPARISON_ID = "cmp-20260911-yjf-off-guarded-ab"
RUN_METADATA_FILENAME = "运行元数据与脱敏摘要.md"
HUMAN_REVIEW_FILENAME = "_human_review.json"
HUMAN_REVIEW_PATH_ENV = "EVAL_COMPARISON_REVIEW_PATH"
LEGACY_KNOWLEDGE_ID_PREFIX = "K-" + "WEBSHELL-"

LEGACY_KNOWLEDGE_ID_MAP = {
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}PRINCIPLE": "WSK-001",
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}FEATURES": "WSK-001",
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}TOOLS-TRAFFIC": "WSK-001",
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}EVIDENCE-CHECKLIST": "WSK-010",
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}RESPONSE-TEMPLATE": "WSK-015",
    f"{LEGACY_KNOWLEDGE_ID_PREFIX}MANUAL-TAKEOVER": "WSK-015",
}
KNOWLEDGE_ID_PATTERN = re.compile(rf"(WSK-\d{{3}}|{LEGACY_KNOWLEDGE_ID_PREFIX}[A-Z-]+)")


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
    if path.is_dir():
        payload = _load_result_package_dir(path)
        return _normalize_payload(payload, min_case_count=MIN_FORMAL_CASE_COUNT)

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包不是合法 JSON: {path}") from exc

    payload = _wrap_payload(raw_payload, source_path=path)
    payload["data_source"] = "actual"
    return _normalize_payload(payload, min_case_count=MIN_FORMAL_CASE_COUNT)


def _load_result_package_dir(path: Path) -> dict[str, Any]:
    summary_path = path / "_summary.json"
    try:
        rows = json.loads(summary_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包缺少 _summary.json: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测结果包 _summary.json 不是合法 JSON: {summary_path}") from exc
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="正式评测结果包 _summary.json 顶层必须是数组")
    return _build_actual_payload_from_summary_rows(rows, package_dir=path)


def _wrap_payload(raw_payload: Any, source_path: Path | None = None) -> dict[str, Any]:
    if isinstance(raw_payload, list):
        if _looks_like_ab_summary_rows(raw_payload):
            return _build_actual_payload_from_summary_rows(raw_payload, package_dir=source_path.parent if source_path else None)
        return {
            "schema_version": MOCK_SCHEMA_VERSION,
            "comparison_id": "cmp-actual-import",
            "generated_at": "",
            "data_source": "actual",
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


def _looks_like_ab_summary_rows(rows: list[Any]) -> bool:
    return bool(rows) and all(isinstance(row, dict) and {"case_id", "mode"}.issubset(row) for row in rows)


def _build_actual_payload_from_summary_rows(rows: list[dict[str, Any]], package_dir: Path | None) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    case_numbers: dict[str, int] = {}
    categories: dict[str, str] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        mode = str(row.get("mode") or "").strip().lower()
        if not case_id or mode not in {"off", "guarded"}:
            raise HTTPException(status_code=500, detail="正式评测结果包行必须包含 case_id 和 off/guarded mode")
        grouped.setdefault(case_id, {})[mode] = row
        case_numbers[case_id] = int(row.get("case_no") or len(case_numbers) + 1)
        categories[case_id] = str(row.get("category") or "unknown")

    human_reviews = _load_human_reviews(package_dir)
    results: list[dict[str, Any]] = []
    for case_id in sorted(grouped, key=lambda item: case_numbers.get(item, 0)):
        pair = grouped[case_id]
        if "off" not in pair or "guarded" not in pair:
            raise HTTPException(status_code=500, detail=f"正式评测结果包案例缺少 OFF/GUARDED 配对: {case_id}")

        case_no = case_numbers[case_id]
        off_report = _read_case_report(package_dir, case_no, "off")
        guarded_report = _read_case_report(package_dir, case_no, "guarded")
        off = _summary_row_to_run_result(pair["off"], off_report)
        guarded = _summary_row_to_run_result(pair["guarded"], guarded_report)
        comparison = _actual_comparison(pair["guarded"], off, guarded)
        human_review, reviewed_winner, reviewed_reason = _human_review(
            case_id,
            pair["guarded"],
            off_report,
            guarded_report,
            human_reviews.get(case_id),
        )
        if reviewed_winner is not None:
            comparison["winner"] = reviewed_winner
            comparison["reason"] = reviewed_reason or "采用结构化人工 Review 结论。"
        results.append(
            {
                "case_id": case_id,
                "knowledge_mode": _knowledge_mode(pair["guarded"]),
                "applicability": _applicability(pair["guarded"]),
                "off": off,
                "guarded": guarded,
                "comparison": comparison,
                "human_review": human_review,
                "_category": categories[case_id],
            }
        )

    return {
        "schema_version": MOCK_SCHEMA_VERSION,
        "comparison_id": ACTUAL_COMPARISON_ID,
        "generated_at": _result_package_generated_at(package_dir),
        "data_source": "actual",
        "suite": {
            "name": "scenario-knowledge-ab",
            "case_count": len(results),
            "baseline": "OFF",
            "candidate": "GUARDED",
            "knowledge_base": "src/sec_agent/deep_agent/knowledge/webshell-knowledge.md",
        },
        "run_metadata": _load_run_metadata(package_dir),
        "results": results,
    }


def _read_case_report(package_dir: Path | None, case_no: int, mode: str) -> dict[str, Any]:
    if package_dir is None:
        return {}
    path = package_dir / f"report_case{case_no}_{mode}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"正式评测报告不是合法 JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"正式评测报告顶层必须是对象: {path.name}")
    return payload


def _summary_row_to_run_result(row: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    case_id = str(row.get("case_id") or "")
    mode = str(row.get("mode") or "")
    matched_knowledge_ids = _extract_knowledge_ids(row)
    tool_names = _unique_strings(row.get("tools_called") or [])
    tool_call_records = [record for record in report.get("tool_call_records") or [] if isinstance(record, dict)]
    step_count = len(tool_call_records) if tool_call_records else len(tool_names)
    evidence_breakdown = {
        "event_evidence_refs": [f"{case_id}:event_basic_info"],
        "tool_result_refs": [f"tool:{tool}:{mode}:{case_id}" for tool in tool_names],
        "knowledge_refs": [f"knowledge:{knowledge_id}" for knowledge_id in matched_knowledge_ids],
    }
    return {
        "verdict": _verdict(row, report),
        "confidence": float(report.get("confidence") or _risk_default_confidence(row.get("risk_level"))),
        "matched_knowledge_ids": matched_knowledge_ids,
        "tool_status": _summary_tool_status(row, tool_call_records),
        "evidence_refs": [],
        "evidence_breakdown": evidence_breakdown,
        "forbidden_conclusion_hit": _forbidden_conclusion_hit(row, matched_knowledge_ids),
        "manual_takeover": bool(report.get("need_manual_takeover", row.get("need_manual_takeover", False))),
        "step_count": step_count,
        "duration_ms": 0,
    }


def _summary_tool_status(row: dict[str, Any], tool_call_records: list[dict[str, Any]]) -> dict[str, str]:
    knowledge_state = _knowledge_tool_state(row)
    mcp_state = _mcp_tool_state(row, tool_call_records)
    notes = (
        f"knowledge_call_count={int(row.get('knowledge_call_count') or 0)}; "
        f"tools_called={len(row.get('tools_called') or [])}; "
        "完整工具输出只保留在内部结果包。"
    )
    return {
        "knowledge_query": knowledge_state,
        "mcp_tools": mcp_state,
        "notes": notes,
    }


def _knowledge_tool_state(row: dict[str, Any]) -> str:
    if not row.get("knowledge_called"):
        return "not_called"
    statuses = [str(item.get("status") or "") for item in row.get("knowledge_statuses") or [] if isinstance(item, dict)]
    if "success" in statuses:
        return "success"
    if "partial" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    return "skipped"


def _mcp_tool_state(row: dict[str, Any], tool_call_records: list[dict[str, Any]]) -> str:
    records = [record for record in tool_call_records if record.get("tool") != "knowledge_query"]
    statuses = [str(record.get("status") or "") for record in records]
    if not statuses:
        tool_names = [name for name in row.get("tools_called") or [] if name != "knowledge_query"]
        return "success" if tool_names else "skipped"
    if all(status == "success" for status in statuses):
        return "success"
    if all(status == "failed" for status in statuses):
        return "failed"
    return "partial"


def _extract_knowledge_ids(row: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for item in row.get("knowledge_statuses") or []:
        if not isinstance(item, dict) or item.get("status") != "success":
            continue
        candidates.extend(KNOWLEDGE_ID_PATTERN.findall(str(item.get("error") or "")))
    for ref in row.get("knowledge_refs_in_report") or []:
        candidates.extend(KNOWLEDGE_ID_PATTERN.findall(str(ref)))
    return _canonical_knowledge_ids(candidates)


def _canonical_knowledge_ids(values: list[Any]) -> list[str]:
    ids: list[str] = []
    for value in values:
        text = str(value)
        canonical = LEGACY_KNOWLEDGE_ID_MAP.get(text, text)
        if canonical and canonical not in ids:
            ids.append(canonical)
    return ids


def _knowledge_mode(row: dict[str, Any]) -> str:
    match str(row.get("gate_decision") or ""):
        case "in_scope":
            return "knowledge_required"
        case "weak_signal":
            return "knowledge_optional"
        case "out_of_scope":
            return "knowledge_forbidden"
        case _:
            return "knowledge_not_applicable"


def _applicability(row: dict[str, Any]) -> str:
    match str(row.get("gate_decision") or ""):
        case "in_scope":
            return "applicable"
        case "weak_signal":
            return "partially_applicable"
        case "out_of_scope":
            return "not_applicable"
        case _:
            return "unknown"


def _actual_comparison(guarded_row: dict[str, Any], off: dict[str, Any], guarded: dict[str, Any]) -> dict[str, Any]:
    confidence_delta = round(float(guarded["confidence"]) - float(off["confidence"]), 4)
    step_delta = int(guarded["step_count"]) - int(off["step_count"])
    duration_delta_ms = int(guarded["duration_ms"]) - int(off["duration_ms"])
    winner = "TIE"
    reason = "自动转换只整理事实字段，不以知识命中自动判定优胜；当前等待结构化人工 Review。"
    if guarded["forbidden_conclusion_hit"]:
        winner = "OFF"
        reason = "GUARDED 命中禁止结论或越界知识引用，按回归处理。"
    return {
        "winner": winner,
        "confidence_delta": confidence_delta,
        "step_delta": step_delta,
        "duration_delta_ms": duration_delta_ms,
        "reason": reason,
    }


def _load_human_reviews(package_dir: Path | None) -> dict[str, dict[str, Any]]:
    configured_path = os.getenv(HUMAN_REVIEW_PATH_ENV)
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    elif package_dir is not None:
        path = package_dir / HUMAN_REVIEW_FILENAME
    else:
        return {}
    if not path.exists():
        if configured_path:
            raise HTTPException(status_code=500, detail=f"结构化人工 Review 不存在: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"结构化人工 Review 不是合法 JSON: {path}") from exc
    rows = payload.get("reviews") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="结构化人工 Review 顶层必须是数组或包含 reviews 数组")
    reviews: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("case_id") or "").strip():
            raise HTTPException(status_code=500, detail="结构化人工 Review 每项必须包含 case_id")
        case_id = str(row["case_id"]).strip()
        if case_id in reviews:
            raise HTTPException(status_code=500, detail=f"结构化人工 Review 存在重复案例: {case_id}")
        reviews[case_id] = row
    return reviews


def _human_review(
    case_id: str,
    guarded_row: dict[str, Any],
    off_report: dict[str, Any],
    guarded_report: dict[str, Any],
    supplied: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None, str]:
    if supplied is None:
        return (
            {
                "status": "pending",
                "reviewer": None,
                "reviewed_at": None,
                "comments": "尚未加载结构化人工 Review；自动转换不替代业务判定。",
                "action_items": _actual_action_items(guarded_row, off_report, guarded_report),
            },
            None,
            "",
        )

    status = str(supplied.get("status") or "").strip()
    if status not in {"pending", "passed", "failed", "needs_follow_up"}:
        raise HTTPException(status_code=500, detail=f"结构化人工 Review 状态非法: {case_id}")
    winner_value = supplied.get("winner")
    winner = str(winner_value).upper() if winner_value is not None else None
    if winner not in {None, "OFF", "GUARDED", "TIE"}:
        raise HTTPException(status_code=500, detail=f"结构化人工 Review winner 非法: {case_id}")
    if status == "pending" and winner is not None:
        raise HTTPException(status_code=500, detail=f"待复核案例不能预先指定 winner: {case_id}")
    action_items = supplied.get("action_items") or []
    if not isinstance(action_items, list):
        raise HTTPException(status_code=500, detail=f"结构化人工 Review action_items 必须是数组: {case_id}")
    return (
        {
            "status": status,
            "reviewer": supplied.get("reviewer"),
            "reviewed_at": supplied.get("reviewed_at"),
            "comments": str(supplied.get("comments") or ""),
            "action_items": _unique_strings(action_items),
        },
        winner,
        str(supplied.get("reason") or ""),
    )


def _actual_action_items(guarded_row: dict[str, Any], off_report: dict[str, Any], guarded_report: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if not off_report or not guarded_report:
        items.append("结果包未提供完整 report_caseN_off/guarded.json，当前按 _summary.json 生成汇总。")
    if str(guarded_row.get("gate_decision")) == "in_scope":
        items.append("人工复核 in_scope 案例的 WSK 命中与知识引用是否符合正式评测口径。")
    if guarded_row.get("need_manual_takeover"):
        items.append("人工复核 manual_takeover=true 是否符合证据不足或高风险处置边界。")
    return items


def _forbidden_conclusion_hit(row: dict[str, Any], matched_knowledge_ids: list[str]) -> bool:
    gate_decision = str(row.get("gate_decision") or "")
    if gate_decision in {"weak_signal", "out_of_scope"} and matched_knowledge_ids:
        return True
    return False


def _verdict(row: dict[str, Any], report: dict[str, Any]) -> str:
    conclusion = str(report.get("conclusion") or row.get("conclusion") or "")
    if any(token in conclusion for token in ("证据不足", "无法得出明确")):
        return "uncertain"
    if any(token in conclusion for token in ("误报", "合法业务", "良性")):
        return "benign"
    if any(token in conclusion for token in ("攻击", "WebShell", "恶意")):
        return "malicious"
    return "uncertain"


def _risk_default_confidence(risk_level: Any) -> float:
    match str(risk_level or "").upper():
        case "CRITICAL":
            return 0.85
        case "HIGH":
            return 0.75
        case "MEDIUM":
            return 0.55
        case "LOW":
            return 0.35
        case _:
            return 0.0


def _result_package_generated_at(package_dir: Path | None) -> str:
    if package_dir is None:
        return "2026-09-11T00:00:00+08:00"
    readme = package_dir / "README.md"
    if not readme.exists():
        return "2026-09-11T00:00:00+08:00"
    text = readme.read_text(encoding="utf-8")
    match = re.search(r"生成时间：(\d{4}-\d{2}-\d{2})", text)
    if match:
        return f"{match.group(1)}T00:00:00+08:00"
    return "2026-09-11T00:00:00+08:00"


def _load_run_metadata(package_dir: Path | None) -> dict[str, Any]:
    default = {
        "result_package_name": package_dir.name if package_dir else "_summary.json",
        "result_package_generated_at": _result_package_generated_at(package_dir),
        "run_commit": None,
        "model": "",
        "tool_mode": "",
        "knowledge_modes": ["off", "guarded"],
        "key_config_notes": [
            "未找到脱敏运行元数据文件；自动转换不会补造 Commit、模型或配置。",
            "逐案例耗时未在结果包中提供，duration_ms 保持 0。",
            "完整 report_*.json 包含测试环境平台数据快照，不提交仓库，不在接口中原样暴露工具输出。",
        ],
    }
    if package_dir is None:
        return default
    path = package_dir / RUN_METADATA_FILENAME
    if not path.exists():
        return default

    text = path.read_text(encoding="utf-8")
    run_commit = _first_code_value(_metadata_table_value(text, "运行 Commit")) or None
    code_baseline = _metadata_table_value(text, "代码基线")
    model = _first_code_value(_metadata_table_value(text, "LLM 模型"))
    tool_mode = _first_code_value(_metadata_table_value(text, "工具模式"))
    run_time = _metadata_table_value(text, "运行时间")
    max_steps = _metadata_table_value(text, "调查步数上限")
    max_tool_calls = _metadata_table_value(text, "工具调用硬上限")
    mcp_timeout = _metadata_table_value(text, "MCP 单次超时")
    notes = [
        f"代码基线：{code_baseline}" if code_baseline else "",
        f"运行时间：{run_time}" if run_time else "",
        f"调查步数上限：{max_steps}" if max_steps else "",
        f"工具调用硬上限：{max_tool_calls}" if max_tool_calls else "",
        f"MCP 单次超时：{mcp_timeout}" if mcp_timeout else "",
        "逐案例耗时未在结果包中提供，duration_ms 保持 0。",
        "完整 report_*.json 包含测试环境平台数据快照，不提交仓库，不在接口中原样暴露工具输出。",
    ]
    return {
        **default,
        "run_commit": run_commit,
        "model": model,
        "tool_mode": tool_mode,
        "key_config_notes": [note for note in notes if note],
    }


def _metadata_table_value(text: str, label: str) -> str:
    pattern = re.compile(rf"^\|\s*{re.escape(label)}\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _first_code_value(value: str) -> str:
    match = re.search(r"`([^`]+)`", value)
    return match.group(1).strip() if match else value.strip()


def _mock_payload() -> dict[str, Any]:
    return _normalize_payload(
        {
            "schema_version": MOCK_SCHEMA_VERSION,
            "comparison_id": "cmp-20260907-mock",
            "generated_at": "2026-09-07T00:00:00+08:00",
            "data_source": "mock_fixture",
            "run_metadata": {
                "result_package_name": "built-in-mock",
                "result_package_generated_at": "2026-09-07T00:00:00+08:00",
                "run_commit": None,
                "model": "mock",
                "tool_mode": "mock_fixture",
                "knowledge_modes": ["off", "guarded"],
                "key_config_notes": ["内置 Mock 仅用于前端联调，不代表真实评测结果。"],
            },
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
                            "WSK-001",
                            "WSK-010",
                        ],
                        "tool_status": {
                            "knowledge_query": "success",
                            "mcp_tools": "skipped",
                            "notes": "GUARDED 组命中知识并补充证据引用。",
                        },
                        "evidence_refs": [
                            "case1:alert",
                            "tool:knowledge_query:case1",
                            "knowledge:WSK-001",
                            "knowledge:WSK-010",
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
                        "matched_knowledge_ids": ["WSK-015"],
                        "tool_status": {
                            "knowledge_query": "success",
                            "mcp_tools": "failed",
                            "notes": "GUARDED 组引用人工接管规则，不编造工具结果。",
                        },
                        "evidence_refs": [
                            "case5:simulated-tool-failure",
                            "tool:mcp:case5",
                            "tool:knowledge_query:case5",
                            "knowledge:WSK-015",
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
        "comparison_id": payload.get("comparison_id") or "cmp-actual-import",
        "generated_at": payload.get("generated_at") or "",
        "data_source": payload.get("data_source") or "mock_fixture",
        "suite": suite,
        "run_metadata": payload.get("run_metadata"),
        "summary": _build_summary(normalized_results),
        "results": normalized_results,
    }


def _normalize_case_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in result.items() if not key.startswith("_")}
    normalized["off"] = _normalize_run_result(normalized["off"])
    normalized["guarded"] = _normalize_run_result(normalized["guarded"])
    normalized["comparison"] = _normalize_comparison(normalized)
    return normalized


def _normalize_run_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    normalized["matched_knowledge_ids"] = _canonical_knowledge_ids(normalized.get("matched_knowledge_ids") or [])
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
    normalized["evidence_refs"] = _unique_strings(normalized.get("evidence_refs") or [])
    return normalized


def _build_evidence_breakdown(evidence_refs: list[str], matched_knowledge_ids: list[str]) -> dict[str, list[str]]:
    event_refs: list[str] = []
    tool_refs: list[str] = []
    knowledge_refs: list[str] = []
    for ref in _unique_strings(evidence_refs):
        if _is_knowledge_ref(ref):
            knowledge_refs.append(_canonical_evidence_ref(ref))
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
    return ref.startswith("knowledge:") or ref.startswith(("K-", "WSK-"))


def _canonical_evidence_ref(ref: str) -> str:
    if not ref.startswith("knowledge:"):
        return LEGACY_KNOWLEDGE_ID_MAP.get(ref, ref)
    _, _, raw_knowledge_id = ref.partition(":")
    return f"knowledge:{LEGACY_KNOWLEDGE_ID_MAP.get(raw_knowledge_id, raw_knowledge_id)}"


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
