from __future__ import annotations

from sec_agent.domain.models import BusinessStatus, EventContext, TimelineEntry


ALLOWED_TRANSITIONS: dict[BusinessStatus, set[BusinessStatus]] = {
    BusinessStatus.RECEIVED: {BusinessStatus.CORRELATING, BusinessStatus.FAILED},
    BusinessStatus.CORRELATING: {BusinessStatus.TRIAGED, BusinessStatus.FAILED},
    BusinessStatus.TRIAGED: {
        BusinessStatus.INVESTIGATING,
        BusinessStatus.COMPLETED,
        BusinessStatus.HUMAN_REQUIRED,
        BusinessStatus.FAILED,
    },
    BusinessStatus.INVESTIGATING: {
        BusinessStatus.DECISION_READY,
        BusinessStatus.HUMAN_REQUIRED,
        BusinessStatus.FAILED,
    },
    BusinessStatus.DECISION_READY: {
        BusinessStatus.APPROVAL_REQUIRED,
        BusinessStatus.EXECUTING,
        BusinessStatus.HUMAN_REQUIRED,
        BusinessStatus.FAILED,
    },
    BusinessStatus.APPROVAL_REQUIRED: {
        BusinessStatus.EXECUTING,
        BusinessStatus.HUMAN_REQUIRED,
        BusinessStatus.FAILED,
    },
    BusinessStatus.EXECUTING: {BusinessStatus.VERIFYING, BusinessStatus.FAILED},
    BusinessStatus.VERIFYING: {
        BusinessStatus.COMPLETED,
        BusinessStatus.DECISION_READY,
        BusinessStatus.HUMAN_REQUIRED,
        BusinessStatus.FAILED,
    },
    BusinessStatus.COMPLETED: set(),
    BusinessStatus.HUMAN_REQUIRED: set(),
    BusinessStatus.FAILED: set(),
}


class InvalidStatusTransition(ValueError):
    pass


class StateMachine:
    """状态只能由编排层调用该状态机推进。"""

    def move(self, ctx: EventContext, next_status: BusinessStatus, message: str) -> EventContext:
        allowed = ALLOWED_TRANSITIONS[ctx.status]
        if next_status not in allowed:
            raise InvalidStatusTransition(f"非法状态流转: {ctx.status} -> {next_status}")

        ctx.status = next_status
        ctx.timeline.append(TimelineEntry(status=next_status, message=message))
        return ctx

