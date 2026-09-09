# -*- coding: utf-8 -*-
"""T0905-07 端到端 A/B：真正跑 LLM 调查，验证 Agent 知识增强的真实能力。

与 ab_gatekeeper.py（确定性、无需 LLM，验证门禁+工具契约）互补，本脚本走完整
investigate()：让 LLM 实际规划调查、调用工具（含 knowledge_query），对比
off / guarded 两种 KNOWLEDGE_MODE 下最终调查报告是否真正用上知识。

观察指标（Agent 真实能力，而非工具契约）：
  1. knowledge_query 是否被 LLM 实际调用（tool_call_records 中出现）；
  2. 报告 evidence_source 是否提炼进知识来源 URL（知识包引用）；
  3. off vs guarded 报告的实质差异（是否有知识增强）。

用法（项目根目录，需配置 LLM_BASE_URL/LLM_API_KEY 或 llm_config.local.json）：
  PYTHONPATH=src python scripts/e2e_ab_gatekeeper.py --cases 1,6,7,8,9,10
  PYTHONPATH=src python scripts/e2e_ab_gatekeeper.py --cases 9 --out-dir _knowledge_cases/e2e
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sec_agent.deep_agent.config import load_config
from sec_agent.deep_agent.llm import LLMClient
from sec_agent.deep_agent.models import SecurityEventInput
from sec_agent.deep_agent.agent import DeepInvestigationAgent
from sec_agent.deep_agent.main import build_tools

CASES = ROOT / "docs" / "modules" / "scenario-knowledge" / "knowledge-test-cases"

CASE_METADATA = {
    1: ("TC-KNOWLEDGE-001", "正向变体"),
    2: ("TC-KNOWLEDGE-002", "正向变体"),
    3: ("TC-KNOWLEDGE-003", "正向变体"),
    4: ("TC-KNOWLEDGE-004", "证据不足"),
    5: ("TC-KNOWLEDGE-005", "证据不足"),
    6: ("TC-KNOWLEDGE-006", "负向对照"),
    7: ("TC-KNOWLEDGE-007", "合法业务误报"),
    8: ("TC-KNOWLEDGE-008", "弱信号/证据不足"),
    9: ("TC-KNOWLEDGE-009", "正向变体"),
    10: ("TC-KNOWLEDGE-010", "负向对照"),
}


def load_event(i: int):
    raw = json.loads((CASES / f"case{i}.json").read_text(encoding="utf-8"))
    if "input_event" in raw:
        return raw["input_event"], raw["case_id"], raw.get("category", "")
    return raw, CASE_METADATA[i][0], CASE_METADATA[i][1]


def run_one(mode: str, i: int) -> dict:
    os.environ["KNOWLEDGE_MODE"] = mode
    config = load_config()
    tools = build_tools(config)
    llm = LLMClient(config.llm)
    agent = DeepInvestigationAgent(config, llm, tools)
    event = SecurityEventInput.from_dict(load_event(i)[0])
    report = agent.investigate(event)
    return report.to_dict()


def summarize(report: dict, mode: str, i: int) -> dict:
    ev, cid, cat = load_event(i)
    records = report.get("tool_call_records") or []
    knowledge_calls = [r for r in records if r.get("tool") == "knowledge_query"]
    evidence_source = report.get("evidence_source") or []
    knowledge_refs = [s for s in evidence_source if "知识包引用" in s]
    gate_decision = ""
    if knowledge_calls:
        first = knowledge_calls[0]
        gate_decision = (first.get("output") or "")
    return {
        "case_no": i,
        "case_id": cid,
        "category": cat,
        "mode": mode,
        "tools_called": [r.get("tool") for r in records],
        "knowledge_called": len(knowledge_calls) > 0,
        "knowledge_call_count": len(knowledge_calls),
        "knowledge_refs_in_report": knowledge_refs,
        "need_manual_takeover": report.get("need_manual_takeover"),
        "risk_level": report.get("risk_level"),
        "conclusion": (report.get("conclusion") or "")[:80],
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    parser = argparse.ArgumentParser(description="T0905-07 端到端 A/B（真实 LLM 调查）")
    parser.add_argument("--cases", default="1,6,7,8,9,10", help="逗号分隔 case 编号")
    parser.add_argument("--out-dir", default="", help="完整报告 JSON 输出目录（可选）")
    args = parser.parse_args(argv)

    case_ids = [int(x) for x in args.cases.split(",") if x.strip()]

    if not LLMClient(load_config().llm).available:
        print("错误：LLM 未配置。请设置 LLM_BASE_URL/LLM_API_KEY 或 llm_config.local.json。", file=sys.stderr)
        return 1

    print("=== 端到端 A/B（真实 LLM 调查）：off vs guarded 知识增强 ===", flush=True)
    for i in case_ids:
        for mode in ("guarded", "off"):
            report = run_one(mode, i)
            r = summarize(report, mode, i)
            called = "调用✓" if r["knowledge_called"] else "未调用"
            refs = r["knowledge_refs_in_report"]
            ref_note = f"报告含知识引用✓({len(refs)}条)" if refs else "报告无知识引用"
            takeover = "人工接管" if r["need_manual_takeover"] else "自动结论"
            print(
                f"case{r['case_no']:<2} {r['category']:<10} {r['mode']:<8} "
                f"knowledge_query={called} | {ref_note} | {takeover} | {r['risk_level']}",
                flush=True,
            )
            print(f"     结论: {r['conclusion']}", flush=True)
            if r["tools_called"]:
                print(f"     工具调用: {r['tools_called']}", flush=True)
            if args.out_dir:
                out = Path(args.out_dir)
                out.mkdir(parents=True, exist_ok=True)
                (out / f"report_case{i}_{mode}.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
