from __future__ import annotations

from dataclasses import dataclass

from sec_agent.core.config import Settings, load_settings
from sec_agent.platforms.base import PlatformAdapter
from sec_agent.platforms.fixed_sample import FixedSampleAdapter
from sec_agent.platforms.jsonl_sample import JsonlSampleAdapter
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
    orchestrator = Orchestrator(platform=platform, store=repository)
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
        return JsonlSampleAdapter(settings.jsonl_sample_dir)
    raise ValueError(f"未知平台接入后端: {settings.platform_backend}")


def _build_repository(settings: Settings) -> EventRepository:
    if settings.storage_backend == "memory":
        return InMemoryEventRepository()
    if settings.storage_backend == "mysql":
        from sec_agent.repositories.mysql import MySQLEventRepository

        return MySQLEventRepository(settings.mysql_dsn, auto_create_schema=settings.mysql_auto_create_schema)
    raise ValueError(f"未知存储后端: {settings.storage_backend}")
