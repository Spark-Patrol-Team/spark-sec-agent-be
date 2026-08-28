from __future__ import annotations

from dataclasses import dataclass

from sec_agent.core.config import Settings, load_settings
from sec_agent.platforms.base import PlatformAdapter
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
from sec_agent.platforms.xdr_openapi import XdrOpenApiAdapter, XdrOpenApiConfig
from sec_agent.repositories.base import EventRepository
from sec_agent.repositories.memory import InMemoryEventRepository
from sec_agent.services.orchestrator import Orchestrator


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    platform: PlatformAdapter
    repository: EventRepository
    orchestrator: Orchestrator


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or load_settings()
    platform = _build_platform(resolved_settings)
    repository = _build_repository(resolved_settings)
    orchestrator = Orchestrator(
        platform=platform,
        store=repository,
        investigation_backend=resolved_settings.investigation_backend,
    )
    return AppContainer(
        settings=resolved_settings,
        platform=platform,
        repository=repository,
        orchestrator=orchestrator,
    )


def _build_platform(settings: Settings) -> PlatformAdapter:
    if settings.platform_backend == "fixed_sample":
        return FixedSampleAdapter()
    if settings.platform_backend == "jsonl_sample":
        return JsonlSampleAdapter(settings.jsonl_sample_dir, input_mode=settings.jsonl_input_mode)
    if settings.platform_backend == "xdr_openapi":
        return XdrOpenApiAdapter(
            XdrOpenApiConfig(
                base_url=settings.xdr_base_url,
                auth_type=settings.xdr_auth_type,
                token=settings.xdr_token,
                access_key=settings.xdr_access_key,
                secret_key=settings.xdr_secret_key,
                alerts_path=settings.xdr_alerts_path,
                connect_timeout_seconds=settings.xdr_connect_timeout_seconds,
                read_timeout_seconds=settings.xdr_read_timeout_seconds,
                startup_check=settings.xdr_startup_check,
                preflight_http_check=settings.xdr_preflight_http_check,
                allow_fixed_sample_fallback=settings.xdr_allow_fixed_sample_fallback,
            ),
            fallback_adapter=FixedSampleAdapter(),
        )
    raise ValueError(f"未知平台接入后端: {settings.platform_backend}")


def _build_repository(settings: Settings) -> EventRepository:
    if settings.storage_backend == "memory":
        return InMemoryEventRepository()
    if settings.storage_backend == "mysql":
        from sec_agent.repositories.mysql import MySQLEventRepository

        return MySQLEventRepository(settings.mysql_dsn, auto_create_schema=settings.mysql_auto_create_schema)
    raise ValueError(f"未知存储后端: {settings.storage_backend}")
