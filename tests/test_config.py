import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sec_agent.core.config import build_mysql_dsn, load_dotenv, parse_bool


class ConfigTest(unittest.TestCase):
    def test_parse_bool_accepts_common_true_values(self) -> None:
        for value in ["true", "True", "1", "yes", "Y", "on"]:
            self.assertTrue(parse_bool(value))

    def test_parse_bool_rejects_false_values(self) -> None:
        for value in ["false", "0", "no", "off", ""]:
            self.assertFalse(parse_bool(value))

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
            with patch.dict(os.environ, {"APP_NAME": "from-env"}, clear=False):
                load_dotenv(env_path)
                self.assertEqual(os.environ["APP_NAME"], "from-env")
                self.assertEqual(os.environ["APP_ENV"], "dev")


if __name__ == "__main__":
    unittest.main()

