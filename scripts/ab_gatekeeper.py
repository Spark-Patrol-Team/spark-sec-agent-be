#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T0905-07 可复制 A/B 运行入口（确定性，无需 LLM）。

对照 KNOWLEDGE_MODE=off / guarded 下 knowledge_query 的注册与放行行为：
  - off     ：knowledge_query 不注册（LLM 无此工具，任何 case 都不会返回知识）；
  - guarded ：knowledge_query 注册，按杨嘉琪三档 gate_decision 放行：
                in_scope     → success（返回知识卡）
                weak_signal  → partial（不返回确认性知识）
                out_of_scope → failed(knowledge_scope_mismatch)

正式案例目录：docs/modules/scenario-knowledge/knowledge-test-cases（陈敏 case1-10）。
case1-6 为扁平结构（等价 input_event），case7-10 为包裹结构
（{case_id, category, description, input_event}）。

三档 gate_decision 来自 WebShellGatekeeper().audit(event).gate_decision.value；
不再读取旧 overall_strength，也不做六档→三档二次映射。

用法（在项目根目录）：
  PYTHONPATH=src python scripts/ab_gatekeeper.py                        # guarded 跑 10 案
  PYTHONPATH=src KNOWLEDGE_MODE=off python scripts/ab_gatekeeper.py     # off 对照
  PYTHONPATH=src python scripts/ab_gatekeeper.py --cases 6,7,8,9,10 --out ab_result.json
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
from sec_agent.deep_agent.models import SecurityEventInput               # noqa: E402
from sec_agent.deep_agent.tools.knowledge import build_knowledge_tools   # noqa: E402
from sec_agent.services.gatekeeper import WebShellGatekeeper             # noqa: E402

FORMAL_CASES_DIR = ROOT / "docs" / "modules" / "scenario-knowledge" / "knowledge-test-cases"

# case1-6 为扁平结构，其 case_id/category/description 取自《案例描述.md》。
CASE_METADATA = {
    1: ("TC-KNOWLEDGE-001", "正向变体", "IIS WebShell（UpdateChecker.aspx）"),
    2: ("TC-KNOWLEDGE-002", "正向变体", "PassiveNeuron 中的 ASPX WebShell 部署尝试"),
    3: ("TC-KNOWLEDGE-003", "正向变体", "Beima WebShell（WordPress/cPanel）"),
    4: ("TC-KNOWLEDGE-004", "证据不足", "单条告警，缺少上下文"),
    5: ("TC-KNOWLEDGE-005", "证据不足", "XDR 查询失败"),
    6: ("TC-KNOWLEDGE-006", "纯非WebShell负向对照", "WordPress插件/供应链异常，无WebShell证据"),
}

DEFAULT_CASES = list(range(1, 11))


def load_case(i: int) -> dict:
    raw = json.loads((FORMAL_CASES_DIR / f"case{i}.json").read_text(encoding="utf-8"))
    if "input_event" in raw:
        # case7-10 包裹结构
        return raw
    case_id, category, description = CASE_METADATA[i]
    return {"case_id": case_id, "category": category, "description": description, "input_event": raw}


def main(argv=None) -> int:
    # Windows 终端默认 GBK，显式切 UTF-8 避免中文乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="T0905-07 门禁 A/B 运行入口（确定性）")
    parser.add_argument("--cases", help="逗号分隔 case 编号，默认 1-10")
    parser.add_argument("--mode", choices=["off", "guarded"], help="覆盖 KNOWLEDGE_MODE")
    parser.add_argument("--out", help="结果 JSON 输出文件（默认打印到 stdout）")
    parser.add_argument("--keyword", default="WebShell 植入方式", help="knowledge_query 检索关键词")
    args = parser.parse_args(argv)

    if args.mode:
        os.environ["KNOWLEDGE_MODE"] = args.mode

    config = load_config()
    mode = config.tools.knowledge_mode
    knowledge_registered = (mode == "guarded")

    case_ids = (
        [int(x) for x in (args.cases or "").split(",") if x.strip()]
        if args.cases else DEFAULT_CASES
    )

    rows = []
    for i in case_ids:
        case = load_case(i)
        event = SecurityEventInput.from_dict(case["input_event"])
        gate = WebShellGatekeeper().audit(event)
        gate_decision = gate.gate_decision.value          # 三档（正式门禁）

        row = {
            "case_no": i,
            "case_id": case["case_id"],
            "category": case["category"],
            "event_type": case["input_event"]["event_type"],
            "mode": mode,
            "knowledge_registered": knowledge_registered,
            "gate_decision": gate_decision,
        }

        if knowledge_registered:
            tool = build_knowledge_tools(gate_decision=gate_decision)[0]
            result = tool.call({"keyword": args.keyword})
            row["knowledge_status"] = result.status
            row["knowledge_error"] = result.error or ""
            row["knowledge_id"] = (result.data or {}).get("knowledge_id", "")
        else:
            row["knowledge_status"] = "not_registered"
            row["knowledge_error"] = ""
            row["knowledge_id"] = ""

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
        elif result == "partial":
            result = "partial(弱信号不返回确认性知识)"
        elif result == "success":
            result = f"success({r['knowledge_id']})"
        print(
            f"case{r['case_no']:<2} {r['category']:<12} "
            f"三档={r['gate_decision']:<12} 知识={result}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
