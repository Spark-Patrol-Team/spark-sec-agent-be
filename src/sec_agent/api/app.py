from __future__ import annotations

from fastapi import FastAPI

from sec_agent.api.routes import events, health, metrics
from sec_agent.bootstrap.container import AppContainer, build_container


def create_app(container: AppContainer | None = None) -> FastAPI:
    app = FastAPI(title="Spark Security Agent Backend", version="0.1.0")
    app.state.container = container or build_container()
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(metrics.router)
    return app


app = create_app()

