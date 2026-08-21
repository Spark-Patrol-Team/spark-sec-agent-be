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
    platform_backend: Literal["fixed_sample"] = "fixed_sample"
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
        mysql_dsn=os.getenv("MYSQL_DSN") or build_mysql_dsn(),
        mysql_auto_create_schema=parse_bool(os.getenv("MYSQL_AUTO_CREATE_SCHEMA", "true")),
    )


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return

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


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
