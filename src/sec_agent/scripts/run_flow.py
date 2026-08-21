from __future__ import annotations

from sec_agent.bootstrap.container import build_container
from sec_agent.domain.models import ApprovalDecision, StartRunRequest


def main() -> None:
    container = build_container()
    ctx = container.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
    print(f"启动完成: event_id={ctx.event_id}, status={ctx.status}")

    if ctx.status == "APPROVAL_REQUIRED":
        ctx = container.orchestrator.approve(
            ctx.event_id,
            ApprovalDecision(
                approved=True,
                approver="local-flow",
                reason="本地主流程演示审批",
                idempotency_key=f"{ctx.event_id}:local-flow-approval",
            ),
        )
        print(f"审批后状态: event_id={ctx.event_id}, status={ctx.status}")

    print("状态时间线:")
    for item in ctx.timeline:
        print(f"- {item.status}: {item.message}")


if __name__ == "__main__":
    main()

