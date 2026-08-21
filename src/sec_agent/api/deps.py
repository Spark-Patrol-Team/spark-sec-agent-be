from __future__ import annotations

from fastapi import Request

from sec_agent.bootstrap.container import AppContainer
from sec_agent.services.orchestrator import Orchestrator


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_orchestrator(request: Request) -> Orchestrator:
    return get_container(request).orchestrator

