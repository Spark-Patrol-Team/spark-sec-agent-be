from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, Field


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
