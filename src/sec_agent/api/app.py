from __future__ import annotations

from fastapi import FastAPI

from sec_agent.api.routes import events, health, metrics
from sec_agent.bootstrap.container import AppContainer, build_container


def create_app(container: AppContainer | None = None, *, build_runtime_container: bool = True) -> FastAPI:
    app = FastAPI(
        title="Spark Security Agent Backend",
        version="0.1.0",
        description="安全事件智能处置后端 MVP 接口文档。",
        openapi_tags=[
            {"name": "health", "description": "服务健康检查接口。"},
            {"name": "events", "description": "安全事件主流程、查询和审批接口。"},
            {"name": "metrics", "description": "MVP 基础统计指标接口。"},
        ],
    )
    if container is not None:
        app.state.container = container
    elif build_runtime_container:
        app.state.container = build_container()
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(metrics.router)
    return app


app = create_app()
