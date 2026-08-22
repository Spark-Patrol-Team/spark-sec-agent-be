import json
import tempfile
import unittest
from pathlib import Path

from sec_agent.scripts.generate_openapi import generate_openapi


class OpenApiGenerationTest(unittest.TestCase):
    def test_generate_openapi_writes_swagger_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "openapi.json"

            schema = generate_openapi(output_path)
            written_schema = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(schema["openapi"], written_schema["openapi"])
            self.assertIn("/runs", written_schema["paths"])
            self.assertIn("/events/{event_id}/approval", written_schema["paths"])
            self.assertEqual(
                written_schema["paths"]["/runs"]["post"]["operationId"],
                "start_event_run",
            )


if __name__ == "__main__":
    unittest.main()
