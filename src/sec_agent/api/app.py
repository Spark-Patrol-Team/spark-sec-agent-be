from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sec_agent.api.routes import events, health, metrics
from sec_agent.bootstrap.container import AppContainer, build_container
from sec_agent.core.config import Settings


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
    runtime_container = container
    if runtime_container is None and build_runtime_container:
        runtime_container = build_container()
    if runtime_container is not None:
        configure_cors(app, runtime_container.settings)
        app.state.container = runtime_container
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(metrics.router)
    return app


def configure_cors(app: FastAPI, settings: Settings) -> None:
    if not settings.cors_allowed_origins and not settings.cors_allowed_origin_regex:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
    )


app = create_app()
