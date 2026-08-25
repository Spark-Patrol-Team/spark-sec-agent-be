from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from sec_agent.api.app import create_app
from sec_agent.bootstrap.container import build_container
from sec_agent.core.config import Settings


class ApiHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            app_env="test",
            storage_backend="memory",
            platform_backend="fixed_sample",
            investigation_backend="tool_mock",
        )
        self.client = TestClient(create_app(container=build_container(settings)))

    def test_health_reports_runtime_settings(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["app_env"], "test")
        self.assertEqual(payload["storage_backend"], "memory")
        self.assertEqual(payload["platform_backend"], "fixed_sample")

    def test_event_http_flow_reaches_completed_after_approval(self) -> None:
        start_response = self.client.post(
            "/runs",
            json={"source": "fixed_sample", "sample_id": "webshell-001"},
        )

        self.assertEqual(start_response.status_code, 200)
        started = start_response.json()
        event_id = started["event_id"]
        self.assertEqual(started["status"], "APPROVAL_REQUIRED")

        detail_response = self.client.get(f"/events/{event_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["event_id"], event_id)

        timeline_response = self.client.get(f"/events/{event_id}/timeline")
        self.assertEqual(timeline_response.status_code, 200)
        self.assertEqual(
            [item["status"] for item in timeline_response.json()],
            [
                "RECEIVED",
                "CORRELATING",
                "TRIAGED",
                "INVESTIGATING",
                "DECISION_READY",
                "APPROVAL_REQUIRED",
            ],
        )

        approval_response = self.client.post(
            f"/events/{event_id}/approval",
            json={
                "approved": True,
                "approver": "api-test",
                "reason": "HTTP 接口测试审批",
                "idempotency_key": "api-approval-test-001",
            },
        )

        self.assertEqual(approval_response.status_code, 200)
        approved = approval_response.json()
        self.assertEqual(approved["status"], "COMPLETED")
        self.assertEqual(approved["response"]["execution"]["status"], "success")
        self.assertEqual(approved["response"]["verification"]["final_status"], "COMPLETED")

        list_response = self.client.get("/events")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(list_response.json()[0]["event_id"], event_id)

        metrics_response = self.client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json()
        self.assertEqual(metrics["total_events"], 1)
        self.assertEqual(metrics["completed_events"], 1)
        self.assertEqual(metrics["human_required_events"], 0)
        self.assertEqual(metrics["failed_events"], 0)

    def test_missing_event_returns_404(self) -> None:
        detail_response = self.client.get("/events/missing-event")
        timeline_response = self.client.get("/events/missing-event/timeline")
        approval_response = self.client.post(
            "/events/missing-event/approval",
            json={
                "approved": True,
                "approver": "api-test",
                "reason": "不存在事件审批",
                "idempotency_key": "api-missing-approval",
            },
        )

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(timeline_response.status_code, 404)
        self.assertEqual(approval_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
