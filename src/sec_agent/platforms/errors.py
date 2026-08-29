from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformIngestError(RuntimeError):
    """平台告警接入失败，供主链统一记录和前端展示。"""

    kind: str
    message: str
    retryable: bool = False
    allow_fallback: bool = False
    platform_status: str | None = None

    def __str__(self) -> str:
        status = f"，平台状态={self.platform_status}" if self.platform_status else ""
        retryable = "可重试" if self.retryable else "不可重试"
        fallback = "允许降级" if self.allow_fallback else "不允许降级"
        return f"{self.kind}: {self.message}{status}（{retryable}，{fallback}）"
