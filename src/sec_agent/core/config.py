from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, Field


DEFAULT_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


class Settings(BaseModel):
    app_name: str = "spark-sec-agent-be"
    app_env: Literal["local", "dev", "test", "prod"] = "local"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = True
    storage_backend: Literal["memory", "mysql"] = "memory"
    platform_backend: Literal["fixed_sample", "jsonl_sample"] = "fixed_sample"
    jsonl_sample_dir: Path = Path("tests/fixtures/fixed_alerts")
    jsonl_input_mode: Literal["normalized", "raw"] = "normalized"
    investigation_backend: Literal["auto", "deep_agent", "tool_mock"] = "auto"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_CORS_ALLOWED_ORIGINS))
    cors_allowed_origin_regex: str | None = None
    cors_allow_credentials: bool = False
    cors_allowed_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allowed_headers: list[str] = Field(default_factory=lambda: ["*"])
    mysql_dsn: str = Field(
        default="mysql+pymysql://sec_agent:sec_agent@127.0.0.1:3306/sec_agent?charset=utf8mb4"
    )
    mysql_auto_create_schema: bool = True


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_name=os.getenv("APP_NAME", "spark-sec-agent-be"),
        app_env=os.getenv("APP_ENV", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("API_PORT", "8000")),
        api_reload=parse_bool(os.getenv("API_RELOAD", "true")),
        storage_backend=os.getenv("STORAGE_BACKEND", "memory"),
        platform_backend=os.getenv("PLATFORM_BACKEND", "fixed_sample"),
        jsonl_sample_dir=resolve_project_path(os.getenv("JSONL_SAMPLE_DIR", "tests/fixtures/fixed_alerts")),
        jsonl_input_mode=os.getenv("JSONL_INPUT_MODE", "normalized"),
        investigation_backend=os.getenv("INVESTIGATION_BACKEND", "auto"),
        cors_allowed_origins=parse_csv(os.getenv("CORS_ALLOWED_ORIGINS"), DEFAULT_CORS_ALLOWED_ORIGINS),
        cors_allowed_origin_regex=os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or None,
        cors_allow_credentials=parse_bool(os.getenv("CORS_ALLOW_CREDENTIALS", "false")),
        cors_allowed_methods=parse_csv(os.getenv("CORS_ALLOWED_METHODS"), ["*"]),
        cors_allowed_headers=parse_csv(os.getenv("CORS_ALLOWED_HEADERS"), ["*"]),
        mysql_dsn=os.getenv("MYSQL_DSN") or build_mysql_dsn(),
        mysql_auto_create_schema=parse_bool(os.getenv("MYSQL_AUTO_CREATE_SCHEMA", "true")),
    )


def load_dotenv(path: Path | None = None) -> None:
    for env_path in dotenv_candidates(path):
        if env_path.exists():
            read_dotenv_file(env_path)
            return


def dotenv_candidates(path: Path | None = None) -> list[Path]:
    if path is not None:
        return [path]

    project_root = Path(__file__).resolve().parents[3]
    candidates = [Path.cwd() / ".env", project_root / ".env"]
    deduped: list[Path] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def read_dotenv_file(env_path: Path) -> None:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def build_mysql_dsn() -> str:
    user = quote_plus(os.getenv("MYSQL_USER", "sec_agent"))
    password = quote_plus(os.getenv("MYSQL_PASSWORD", "sec_agent"))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "sec_agent")
    charset = os.getenv("MYSQL_CHARSET", "utf8mb4")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parents[3]
    return project_root / path


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items if items else []
