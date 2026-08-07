"""Health and readiness endpoints."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.database import get_database
from app.version import VERSION

router = APIRouter(tags=["health"])

_STARTED_AT = time.monotonic()


class HealthResponse(BaseModel):
    """Overall service health."""

    status: Literal["ok", "degraded"] = Field(description="Aggregate service status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment")
    uptime_seconds: float = Field(description="Seconds since process start")
    database: Literal["ok", "unavailable"] = Field(description="Database connectivity")


class LivenessResponse(BaseModel):
    status: Literal["alive"]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health including database connectivity",
)
async def health(response: Response) -> HealthResponse:
    """Report service health.

    Returns 503 when the database is unreachable so orchestrators can act on
    the status code rather than having to parse the body.
    """
    settings = get_settings()
    db_ok = await get_database().healthcheck()

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=VERSION,
        environment=str(settings.environment),
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
        database="ok" if db_ok else "unavailable",
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness probe (no dependency checks)",
)
async def liveness() -> LivenessResponse:
    """Liveness only: is the process running and serving?

    Deliberately does not touch the database - a slow database should not cause
    a container restart loop.
    """
    return LivenessResponse(status="alive")


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe (checks dependencies)",
)
async def readiness(response: Response) -> HealthResponse:
    """Readiness: should this instance receive traffic?"""
    return await health(response)
