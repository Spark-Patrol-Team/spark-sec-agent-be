from __future__ import annotations

from fastapi import APIRouter, Depends

from sec_agent.api.deps import get_container
from sec_agent.api.schemas import HealthResponse
from sec_agent.bootstrap.container import AppContainer

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="get_health",
    summary="服务健康检查",
)
def health(container: AppContainer = Depends(get_container)) -> HealthResponse:
    return {
        "status": "ok",
        "app_name": container.settings.app_name,
        "app_env": container.settings.app_env,
        "storage_backend": container.settings.storage_backend,
        "platform_backend": container.settings.platform_backend,
    }
