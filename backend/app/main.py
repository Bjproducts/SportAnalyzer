"""FastAPI application factory and entrypoint."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.database import close_database, init_database
from app.version import VERSION

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down hooks."""
    settings: Settings = get_settings()
    init_database(settings)
    logger.info("application_startup", **settings.safe_summary())
    try:
        yield
    finally:
        await close_database()
        logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    A factory (rather than a module-level singleton) keeps tests able to build
    an isolated app with overridden settings.
    """
    cfg = settings or get_settings()
    configure_logging(cfg.log_level, json_output=cfg.log_json)

    app = FastAPI(
        title=cfg.project_name,
        version=VERSION,
        summary="Shots-on-target analytics for football players.",
        description=(
            "Historical football research API. Percentages are always returned "
            "alongside the sample size they were computed from, and missing "
            "shots-on-target data is excluded from rates rather than treated as zero."
        ),
        lifespan=lifespan,
        # Interactive docs are useful in development but are an information
        # disclosure surface in production.
        docs_url=None if cfg.is_production else "/docs",
        redoc_url=None if cfg.is_production else "/redoc",
        openapi_url=None if cfg.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_origin_regex=cfg.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Admin-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a request id to every log line emitted during the request."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed", duration_ms=round((time.perf_counter() - started) * 1000, 2)
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info("request_completed", status_code=response.status_code, duration_ms=duration_ms)
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=cfg.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": cfg.project_name,
            "health": f"{cfg.api_v1_prefix}/health",
            "players": f"{cfg.api_v1_prefix}/players",
            "docs": "/docs" if not cfg.is_production else "disabled",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=_settings.api_host,
        port=_settings.api_port,
        reload=not _settings.is_production,
    )
