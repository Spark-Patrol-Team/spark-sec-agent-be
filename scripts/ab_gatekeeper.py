#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T0905-04 可复制 A/B 运行入口（确定性，无需 LLM）。

对照 KNOWLEDGE_MODE=off / guarded 下 knowledge_query 的注册与放行行为：
  - off     ：knowledge_query 不注册（LLM 无此工具，任何 case 都不会返回知识）；
  - guarded ：knowledge_query 注册，但域外（OUT_OF_SCOPE）事件被拒绝
              （返回稳定错误码 knowledge_scope_mismatch）。

每个 case 同时打印 WebShellGatekeeper.audit 的 overall_strength（6 档）与
折叠后的三档 scope（OUT / WEAK / CONFIRMED），作为门禁判定的可复现证据。
全程确定性规则（非 LLM），可无密钥复跑。

用法（在项目根目录，需 src 在导入路径上）：
  PYTHONPATH=src python scripts/ab_gatekeeper.py                        # guarded 跑 8 代表性案
  PYTHONPATH=src KNOWLEDGE_MODE=off python scripts/ab_gatekeeper.py     # off 对照
  PYTHONPATH=src python scripts/ab_gatekeeper.py --cases 1,6,9,10 --out ab_result.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sec_agent.deep_agent.config import load_config                      # noqa: E402
from sec_agent.deep_agent.main import build_tools                        # noqa: E402
from sec_agent.deep_agent.models import SecurityEventInput               # noqa: E402
from sec_agent.deep_agent.tools.knowledge import (                       # noqa: E402
    build_knowledge_tools,
    fold_scope,
)
from sec_agent.services.gatekeeper import WebShellGatekeeper             # noqa: E402

CASES_DIR = ROOT / "tests" / "fixtures" / "gatekeeper_cases"

# 任务3 先跑的代表性 8 案：正向(1,9) / 弱信号(8) / 误报(7) / 工具失败(4,5) / 负向(6) / 域外(10)
DEFAULT_CASES = [1, 9, 8, 7, 4, 5, 6, 10]


def load_case(i: int) -> dict:
    with open(CASES_DIR / f"case{i}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None) -> int:
    # Windows 终端默认 GBK，显式切 UTF-8 避免中文乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="A/B 门禁运行入口（确定性）")
    parser.add_argument("--cases", help="逗号分隔 case 编号，默认 1,9,8,7,4,5,6,10")
    parser.add_argument("--mode", choices=["off", "guarded"], help="覆盖 KNOWLEDGE_MODE")
    parser.add_argument("--out", help="结果 JSON 输出文件（默认打印到 stdout）")
    args = parser.parse_args(argv)

    if args.mode:
        os.environ["KNOWLEDGE_MODE"] = args.mode

    config = load_config()
    config.tools.mode = "mock"  # A/B 只关心 knowledge_query，强制 mock 避免连真实 MCP
    mode = config.tools.knowledge_mode

    # 标准7：复查知识工具是否注册（off 不注册）
    registry = build_tools(config)
    knowledge_registered = "knowledge_query" in registry.names()

    case_ids = (
        [int(x) for x in (args.cases or "").split(",") if x.strip()]
        if args.cases else DEFAULT_CASES
    )

    rows = []
    for i in case_ids:
        case = load_case(i)
        event = SecurityEventInput.from_dict(case["input_event"])
        gate = WebShellGatekeeper().audit(event)
        overall = gate.overall_strength.value
        scope = fold_scope(overall)

        row = {
            "case_no": i,
            "case_id": case["case_id"],
            "category": case["category"],
            "event_type": case["input_event"]["event_type"],
            "mode": mode,
            "knowledge_registered": knowledge_registered,
            "overall_strength": overall,
            "scope": scope,
        }

        if knowledge_registered:
            tool = build_knowledge_tools()[0]
            result = tool.call({
                "keyword": "WebShell攻击原理",
                "event_context": {
                    "overall_strength": overall,
                    "upgraded_score": gate.upgraded_score,
                    "investigation_checklist": gate.investigation_checklist,
                    "false_positive_conditions": gate.false_positive_conditions,
                    "evidence_gaps": gate.evidence_gaps,
                },
            })
            row["knowledge_status"] = result.status
            row["knowledge_error"] = result.error or ""
            row["knowledge_scope"] = (result.data or {}).get("scope", "")
        else:
            row["knowledge_status"] = "not_registered"
            row["knowledge_error"] = ""
            row["knowledge_scope"] = ""

        rows.append(row)

    if args.out:
        Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入：{args.out}")

    print(f"=== A/B 对照（KNOWLEDGE_MODE={mode}，knowledge_query {'已注册' if knowledge_registered else '未注册'}）===")
    for r in rows:
        result = r["knowledge_status"]
        if result == "failed":
            result = f"failed({r['knowledge_error']})"
        elif result == "success":
            result = f"success({r['knowledge_scope']})"
        print(
            f"case{r['case_no']:<2} {r['category']:<8} "
            f"6档={r['overall_strength']:<20} 三档={r['scope']:<10} 知识={result}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
