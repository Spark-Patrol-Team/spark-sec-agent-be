import unittest

from sec_agent.platforms.xdr_openapi import XdrOpenApiAdapter, XdrOpenApiConfig


class FakePostResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakePostSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakePostResponse(self.responses.pop(0))


class XdrRealContractTest(unittest.TestCase):
    def config(self):
        return XdrOpenApiConfig(
            base_url="https://xdr.example.test",
            token="sanitized-token",
            alerts_path="/api/xdr/v1/alerts/list",
        )

    def record(self, event_id="alert-redacted-1", name="通用SQL注入攻击"):
        return {
            "uuId": event_id,
            "name": name,
            "severity": 70,
            "srcIp": ["192.168.X.X"],
            "srcPort": [12345],
            "dstIp": ["192.168.Y.Y"],
            "dstPort": [80],
            "hostIp": "192.168.Y.Y",
            "devSourceName": ["STA (REDACTED)"],
            "threatSubTypeDesc": "SQL注入",
            "firstTime": 1700000000,
            "traceBackId": ["network_security_log-REDACTED"],
            "attackState": 2,
            "alertDealAction": "待处置",
        }

    def test_real_shape_maps_to_existing_alert_record(self):
        session = FakePostSession([{"message": "成功", "code": "Success", "data": {
            "total": 1, "pageSize": 10, "page": 1, "item": [self.record()]
        }}])
        alerts = XdrOpenApiAdapter(self.config(), session=session).fetch_alerts()
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.alert_id, "alert-redacted-1")
        self.assertEqual(alert.alert_type, "sql_injection")
        self.assertEqual(alert.raw_severity, "high")
        self.assertEqual(alert.dst_ip, "192.168.Y.Y")
        self.assertEqual(alert.assets, ["192.168.Y.Y"])
        self.assertEqual(alert.occurred_at.isoformat(), "2023-11-15T06:13:20+08:00")
        self.assertEqual(session.calls[0][1]["json"], {"page": 1, "pageSize": 10})

    def test_pagination_deduplicates_by_provider_uuid(self):
        first = {"message": "成功", "code": "Success", "data": {
            "total": 3, "pageSize": 2, "page": 1, "item": [self.record("same"), self.record("first")]
        }}
        second = {"message": "成功", "code": "Success", "data": {
            "total": 3, "pageSize": 2, "page": 2, "item": [self.record("same"), self.record("last")]
        }}
        session = FakePostSession([first, second])
        alerts = XdrOpenApiAdapter(self.config(), session=session).fetch_alerts()
        self.assertEqual([alert.alert_id for alert in alerts], ["same", "first", "last"])
        self.assertEqual([call[1]["json"]["page"] for call in session.calls], [1, 2])

    def test_missing_optional_real_fields_still_normalizes_and_invalid_port_fails(self):
        raw = self.record()
        raw.pop("srcPort")
        raw.pop("dstIp")
        raw["dstPort"] = [70000]
        session = FakePostSession([{"data": {"total": 1, "pageSize": 10, "page": 1, "item": [raw]}}])
        with self.assertRaises(Exception) as ctx:
            XdrOpenApiAdapter(self.config(), session=session).fetch_alerts()
        self.assertEqual(ctx.exception.kind, "field_mapping")


if __name__ == "__main__":
    unittest.main()

