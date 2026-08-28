import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sec_agent.core.config import (
    DEFAULT_CORS_ALLOWED_ORIGINS,
    build_mysql_dsn,
    load_dotenv,
    load_settings,
    parse_bool,
    parse_csv,
    parse_float,
)


class ConfigTest(unittest.TestCase):
    def test_parse_bool_accepts_common_true_values(self) -> None:
        for value in ["true", "True", "1", "yes", "Y", "on"]:
            self.assertTrue(parse_bool(value))

    def test_parse_bool_rejects_false_values(self) -> None:
        for value in ["false", "0", "no", "off", ""]:
            self.assertFalse(parse_bool(value))

    def test_parse_csv_trims_values_and_preserves_empty_override(self) -> None:
        self.assertEqual(parse_csv("http://a.test, http://b.test ,,", ["default"]), ["http://a.test", "http://b.test"])
        self.assertEqual(parse_csv("", ["default"]), [])
        self.assertEqual(parse_csv(None, ["default"]), ["default"])

    def test_parse_float_trims_value(self) -> None:
        self.assertEqual(parse_float(" 2.5 "), 2.5)

    def test_default_cors_origins_include_frontend_dashboard(self) -> None:
        self.assertIn("http://localhost:8080", DEFAULT_CORS_ALLOWED_ORIGINS)
        self.assertIn("http://127.0.0.1:8080", DEFAULT_CORS_ALLOWED_ORIGINS)

    def test_build_mysql_dsn_from_split_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MYSQL_HOST": "db.local",
                "MYSQL_PORT": "3307",
                "MYSQL_USER": "sec_agent",
                "MYSQL_PASSWORD": "p@ss word",
                "MYSQL_DATABASE": "sec_agent_test",
                "MYSQL_CHARSET": "utf8mb4",
            },
            clear=False,
        ):
            self.assertEqual(
                build_mysql_dsn(),
                "mysql+pymysql://sec_agent:p%40ss+word@db.local:3307/sec_agent_test?charset=utf8mb4",
            )

    def test_load_dotenv_does_not_override_existing_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("APP_ENV=dev\nAPP_NAME=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"APP_NAME": "from-env"}, clear=True):
                load_dotenv(env_path)
                self.assertEqual(os.environ["APP_NAME"], "from-env")
                self.assertEqual(os.environ["APP_ENV"], "dev")

    def test_load_settings_reads_xdr_openapi_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PLATFORM_BACKEND": "xdr_openapi",
                "XDR_BASE_URL": "https://xdr.example.test",
                "XDR_AUTH_TYPE": "token",
                "XDR_TOKEN": "unit-test-token",
                "XDR_ALERTS_PATH": "/openapi/alerts",
                "XDR_CONNECT_TIMEOUT_SECONDS": "1.5",
                "XDR_READ_TIMEOUT_SECONDS": "9",
                "XDR_STARTUP_CHECK": "true",
                "XDR_PREFLIGHT_HTTP_CHECK": "false",
                "XDR_ALLOW_FIXED_SAMPLE_FALLBACK": "true",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.platform_backend, "xdr_openapi")
        self.assertEqual(settings.xdr_base_url, "https://xdr.example.test")
        self.assertEqual(settings.xdr_alerts_path, "/openapi/alerts")
        self.assertEqual(settings.xdr_connect_timeout_seconds, 1.5)
        self.assertEqual(settings.xdr_read_timeout_seconds, 9)
        self.assertTrue(settings.xdr_startup_check)
        self.assertFalse(settings.xdr_preflight_http_check)
        self.assertTrue(settings.xdr_allow_fixed_sample_fallback)


if __name__ == "__main__":
    unittest.main()
