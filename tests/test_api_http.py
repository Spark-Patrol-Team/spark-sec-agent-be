from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
            cors_allowed_origins=["http://frontend.test"],
            cors_allow_credentials=True,
        )
        self.client = TestClient(create_app(container=build_container(settings)))

    def test_health_reports_runtime_settings(self) -> None:
        response = self.client.get("/health", headers={"Origin": "http://frontend.test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://frontend.test")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
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
        self.assertEqual(started["requested_source"], "fixed_sample")
        self.assertEqual(started["effective_source"], "fixed_sample")
        self.assertIsNone(started["fallback_source"])

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
        list_item = list_response.json()[0]
        self.assertEqual(list_item["event_id"], event_id)
        self.assertEqual(list_item["requested_source"], "fixed_sample")
        self.assertEqual(list_item["effective_source"], "fixed_sample")
        self.assertEqual(list_item["sample_id"], "webshell-001")
        self.assertIsNone(list_item["xdr_event_id"])
        self.assertEqual(list_item["status_label"], "已完成")
        self.assertEqual(list_item["alert_count"], 2)
        self.assertEqual(list_item["risk_score"], 85)
        self.assertEqual(list_item["priority"], "high")
        self.assertEqual(list_item["verdict"], "malicious")
        self.assertIsNotNone(list_item["created_at"])
        self.assertIsNotNone(list_item["updated_at"])

        view_response = self.client.get(f"/events/{event_id}/view")
        self.assertEqual(view_response.status_code, 200)
        view = view_response.json()
        self.assertEqual(view["event_id"], event_id)
        self.assertEqual(view["status_label"], "已完成")
        self.assertEqual(view["source"]["sample_id"], "webshell-001")
        self.assertEqual(view["source"]["effective"], "fixed_sample")
        self.assertEqual(view["overview"]["title"], "WebShell安全事件")
        self.assertEqual(view["overview"]["alert_count"], 2)
        self.assertEqual(view["overview"]["risk_score"], 85)
        self.assertEqual(view["overview"]["verdict"], "malicious")
        self.assertEqual(view["overview"]["priority"], "high")
        self.assertGreaterEqual(len(view["overview"]["affected_assets"]), 1)
        self.assertEqual(view["response"]["execution_status"], "success")
        self.assertEqual(view["response"]["final_status"], "COMPLETED")
        self.assertEqual(view["investigation"]["tool_result_count"], 2)
        self.assertIn("evidence_sources", view["investigation"])
        self.assertIn("manual_takeover_reason", view["investigation"])
        self.assertNotIn("tool_results", view["investigation"])
        self.assertEqual(
            [item["status_label"] for item in view["timeline"]],
            ["已接收", "关联中", "已研判", "调查中", "待决策", "待审批", "执行中", "验证中", "已完成"],
        )

        update_response = self.client.patch(
            f"/events/{event_id}",
            json={"status": "HUMAN_REQUIRED", "message": "API 测试手动改状态"},
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated["status"], "HUMAN_REQUIRED")
        self.assertEqual(updated["timeline"][-1]["message"], "API 测试手动改状态")

        delete_response = self.client.delete(f"/events/{event_id}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(self.client.get(f"/events/{event_id}").status_code, 404)

        metrics_response = self.client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json()
        self.assertEqual(metrics["total_events"], 0)
        self.assertEqual(metrics["completed_events"], 0)
        self.assertEqual(metrics["human_required_events"], 0)
        self.assertEqual(metrics["failed_events"], 0)

    def test_missing_event_returns_404(self) -> None:
        detail_response = self.client.get("/events/missing-event")
        view_response = self.client.get("/events/missing-event/view")
        timeline_response = self.client.get("/events/missing-event/timeline")
        update_response = self.client.patch(
            "/events/missing-event",
            json={"status": "FAILED", "message": "不存在事件"},
        )
        delete_response = self.client.delete("/events/missing-event")
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
        self.assertEqual(view_response.status_code, 404)
        self.assertEqual(timeline_response.status_code, 404)
        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(approval_response.status_code, 404)

    def test_cors_preflight_allows_configured_origin(self) -> None:
        response = self.client.options(
            "/runs",
            headers={
                "Origin": "http://frontend.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://frontend.test")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertIn("POST", response.headers["access-control-allow-methods"])
        self.assertIn("content-type", response.headers["access-control-allow-headers"].lower())

    def test_cors_preflight_rejects_unconfigured_origin(self) -> None:
        response = self.client.options(
            "/runs",
            headers={
                "Origin": "http://evil.test",
                "Access-Control-Request-Method": "POST",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "http://evil.test")

    def test_xdr_source_requires_xdr_openapi_backend(self) -> None:
        response = self.client.post(
            "/runs",
            json={"source": "xdr", "xdr_event_id": "REAL-XDR-001"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "FAILED")
        self.assertIn("不匹配", payload["errors"][0]["message"])

    def test_eval_comparisons_returns_off_guarded_mock_payload(self) -> None:
        response = self.client.get("/eval/comparisons")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "2026-09-07.eval-comparison.v1")
        self.assertEqual(payload["data_source"], "mock_fixture")
        self.assertEqual(payload["suite"]["baseline"], "OFF")
        self.assertEqual(payload["suite"]["candidate"], "GUARDED")
        self.assertEqual(payload["summary"]["total_cases"], len(payload["results"]))
        self.assertGreaterEqual(payload["summary"]["guarded_wins"], 1)

        first = payload["results"][0]
        self.assertEqual(first["case_id"], "case1")
        self.assertIn("off", first)
        self.assertIn("guarded", first)
        self.assertIn("comparison", first)
        self.assertEqual(first["comparison"]["winner"], "GUARDED")
        self.assertIn("WSK-001", first["guarded"]["matched_knowledge_ids"])
        self.assertEqual(first["guarded"]["evidence_breakdown"]["event_evidence_refs"], ["case1:alert"])
        self.assertEqual(first["guarded"]["evidence_breakdown"]["tool_result_refs"], ["tool:knowledge_query:case1"])
        self.assertEqual(
            first["guarded"]["evidence_breakdown"]["knowledge_refs"],
            ["knowledge:WSK-001", "knowledge:WSK-010"],
        )

    def test_eval_comparisons_reads_actual_result_package_and_builds_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "actual-result-package"
            path.mkdir()
            (path / "README.md").write_text("生成时间：2026-09-11\n模型：deepseek 系列\n", encoding="utf-8")
            rows = []
            for case_no in range(1, 7):
                case_id = f"TC-KNOWLEDGE-{case_no:03d}"
                gate_decision = "in_scope" if case_no == 1 else "weak_signal"
                guarded_statuses = (
                    [{"status": "success", "error": "[知识卡·WSK-001] WebShell 正向调查"}]
                    if case_no == 1
                    else [{"status": "partial", "error": "[部分成功] 当前仅为弱信号"}]
                )
                rows.append(
                    {
                        "case_no": case_no,
                        "case_id": case_id,
                        "category": "正向变体",
                        "mode": "guarded",
                        "gate_decision": gate_decision,
                        "tools_called": ["query_asset", "knowledge_query", "dbproxy_告警数据查询工具"],
                        "knowledge_called": True,
                        "knowledge_call_count": len(guarded_statuses),
                        "knowledge_statuses": guarded_statuses,
                        "knowledge_refs_in_report": [],
                        "need_manual_takeover": True,
                        "risk_level": "HIGH",
                        "conclusion": "证据不足，无法得出明确调查结论",
                    }
                )
                rows.append(
                    {
                        "case_no": case_no,
                        "case_id": case_id,
                        "category": "正向变体",
                        "mode": "off",
                        "gate_decision": gate_decision,
                        "tools_called": ["query_asset", "dbproxy_告警数据查询工具"],
                        "knowledge_called": False,
                        "knowledge_call_count": 0,
                        "knowledge_statuses": [],
                        "knowledge_refs_in_report": [],
                        "need_manual_takeover": True,
                        "risk_level": "HIGH",
                        "conclusion": "证据不足，无法得出明确调查结论",
                    }
                )
            (path / "_summary.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            (path / "report_case1_guarded.json").write_text(
                json.dumps(
                    {
                        "confidence": 0.91,
                        "need_manual_takeover": True,
                        "tool_call_records": [
                            {"tool": "query_asset", "status": "failed"},
                            {"tool": "knowledge_query", "status": "success"},
                            {"tool": "dbproxy_告警数据查询工具", "status": "partial"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (path / "report_case1_off.json").write_text(
                json.dumps(
                    {
                        "confidence": 0.72,
                        "need_manual_takeover": True,
                        "tool_call_records": [
                            {"tool": "query_asset", "status": "failed"},
                            {"tool": "dbproxy_告警数据查询工具", "status": "partial"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"EVAL_COMPARISON_FIXTURE_PATH": str(path)}):
                response = self.client.get("/eval/comparisons")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data_source"], "actual")
        self.assertEqual(payload["comparison_id"], "cmp-20260911-yjf-off-guarded-ab")
        self.assertEqual(payload["suite"]["case_count"], 6)
        self.assertEqual(payload["summary"]["total_cases"], 6)
        self.assertEqual(payload["summary"]["guarded_wins"], 1)
        self.assertEqual(
            payload["summary"]["guarded_wins"] + payload["summary"]["off_wins"] + payload["summary"]["ties"],
            6,
        )
        self.assertEqual(payload["run_metadata"]["result_package_generated_at"], "2026-09-11T00:00:00+08:00")
        self.assertIsNone(payload["run_metadata"]["run_commit"])
        guarded = payload["results"][0]["guarded"]
        self.assertEqual(guarded["matched_knowledge_ids"], ["WSK-001"])
        self.assertEqual(guarded["evidence_refs"], [])
        self.assertEqual(guarded["evidence_breakdown"]["event_evidence_refs"], ["TC-KNOWLEDGE-001:event_basic_info"])
        self.assertIn("tool:knowledge_query:guarded:TC-KNOWLEDGE-001", guarded["evidence_breakdown"]["tool_result_refs"])
        self.assertEqual(guarded["evidence_breakdown"]["knowledge_refs"], ["knowledge:WSK-001"])

    def test_eval_comparisons_rejects_incomplete_actual_fixture(self) -> None:
        incomplete_payload = {
            "schema_version": "2026-09-07.eval-comparison.v1",
            "comparison_id": "cmp-actual-incomplete",
            "generated_at": "2026-09-09T00:00:00+08:00",
            "suite": {
                "name": "scenario-knowledge-formal-ab",
                "case_count": 1,
                "baseline": "OFF",
                "candidate": "GUARDED",
                "knowledge_base": "formal-result-package",
            },
            "results": [self.client.get("/eval/comparisons").json()["results"][0]],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "incomplete_formal_comparison.json"
            path.write_text(json.dumps(incomplete_payload, ensure_ascii=False), encoding="utf-8")
            with mock.patch.dict(os.environ, {"EVAL_COMPARISON_FIXTURE_PATH": str(path)}):
                response = self.client.get("/eval/comparisons")

        self.assertEqual(response.status_code, 500)
        self.assertIn("至少需要 6 案", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
