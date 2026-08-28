import unittest

from sec_agent.scripts.run_flow import build_demo_start_request


class RunFlowTest(unittest.TestCase):
    def test_demo_request_uses_business_source_for_xdr_openapi_backend(self) -> None:
        request = build_demo_start_request("xdr_openapi")

        self.assertEqual(request.source, "xdr")
        self.assertIsNone(request.sample_id)
        self.assertIsNone(request.xdr_event_id)

    def test_demo_request_keeps_fixed_sample_defaults(self) -> None:
        request = build_demo_start_request("fixed_sample")

        self.assertEqual(request.source, "fixed_sample")
        self.assertEqual(request.sample_id, "webshell-001")

    def test_demo_request_keeps_jsonl_sample_defaults(self) -> None:
        request = build_demo_start_request("jsonl_sample")

        self.assertEqual(request.source, "jsonl_sample")
        self.assertEqual(request.sample_id, "FIX-XDR-WEBSHELL-001")


if __name__ == "__main__":
    unittest.main()
