import unittest

from sec_agent.domain.models import ApprovalDecision, BusinessStatus, StartRunRequest
from sec_agent.domain.state_machine import InvalidStatusTransition, StateMachine
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.services.orchestrator import Orchestrator
from sec_agent.storage.memory import InMemoryEventStore


class StateFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = Orchestrator(platform=FixedSampleAdapter(), store=InMemoryEventStore())

    def test_fixed_sample_stops_at_approval_required(self) -> None:
        ctx = self.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))

        self.assertEqual(ctx.status, BusinessStatus.APPROVAL_REQUIRED)
        statuses = [item.status for item in ctx.timeline]
        self.assertEqual(
            statuses,
            [
                BusinessStatus.RECEIVED,
                BusinessStatus.CORRELATING,
                BusinessStatus.TRIAGED,
                BusinessStatus.INVESTIGATING,
                BusinessStatus.DECISION_READY,
                BusinessStatus.APPROVAL_REQUIRED,
            ],
        )
        self.assertIsNotNone(ctx.triage)
        self.assertIsNotNone(ctx.investigation)
        self.assertIsNotNone(ctx.response)
        self.assertTrue(ctx.response.plan.approval_required)

    def test_approval_executes_and_verifies(self) -> None:
        ctx = self.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
        ctx = self.orchestrator.approve(
            ctx.event_id,
            ApprovalDecision(
                approved=True,
                approver="tester",
                reason="单元测试审批",
                idempotency_key="approval-test-001",
            ),
        )

        self.assertEqual(ctx.status, BusinessStatus.COMPLETED)
        statuses = [item.status for item in ctx.timeline]
        self.assertIn(BusinessStatus.EXECUTING, statuses)
        self.assertIn(BusinessStatus.VERIFYING, statuses)
        self.assertEqual(statuses[-1], BusinessStatus.COMPLETED)
        self.assertIsNotNone(ctx.response.execution)
        self.assertIsNotNone(ctx.response.verification)

    def test_duplicate_approval_is_idempotent(self) -> None:
        ctx = self.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
        decision = ApprovalDecision(
            approved=True,
            approver="tester",
            reason="单元测试审批",
            idempotency_key="approval-test-duplicate",
        )

        first = self.orchestrator.approve(ctx.event_id, decision)
        second = self.orchestrator.approve(ctx.event_id, decision)

        self.assertEqual(first.status, BusinessStatus.COMPLETED)
        self.assertEqual(second.status, BusinessStatus.COMPLETED)
        self.assertEqual(
            [item.status for item in first.timeline],
            [item.status for item in second.timeline],
        )

    def test_rejected_approval_goes_human_required(self) -> None:
        ctx = self.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
        ctx = self.orchestrator.approve(
            ctx.event_id,
            ApprovalDecision(
                approved=False,
                approver="tester",
                reason="拒绝高风险动作",
                idempotency_key="approval-test-002",
            ),
        )

        self.assertEqual(ctx.status, BusinessStatus.HUMAN_REQUIRED)

    def test_state_machine_rejects_illegal_transition(self) -> None:
        ctx = self.orchestrator.start(StartRunRequest(source="fixed_sample", sample_id="webshell-001"))
        with self.assertRaises(InvalidStatusTransition):
            StateMachine().move(ctx, BusinessStatus.RECEIVED, "非法回退")


if __name__ == "__main__":
    unittest.main()
