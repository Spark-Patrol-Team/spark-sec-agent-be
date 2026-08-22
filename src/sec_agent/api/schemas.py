from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str
    storage_backend: str
    platform_backend: str


class MetricsResponse(BaseModel):
    total_events: int
    completed_events: int
    human_required_events: int
    failed_events: int
    note: str
