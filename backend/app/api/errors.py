"""Translation of domain exceptions into HTTP responses.

Registered once on the app.  Route handlers and services raise plain domain
exceptions (``app.core.exceptions``); only this module knows about status
codes and response shapes.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.exceptions import ProviderRateLimitError, SotAnalyzerError
from app.core.logging import get_logger

logger = get_logger(__name__)


def _payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SotAnalyzerError)
    logger.warning(
        "domain_error",
        code=exc.code,
        path=request.url.path,
        message=exc.message,
        details=exc.details,
    )
    headers: dict[str, str] = {}
    if isinstance(exc, ProviderRateLimitError) and exc.retry_after_seconds:
        headers["Retry-After"] = str(int(exc.retry_after_seconds))

    return JSONResponse(
        status_code=exc.http_status,
        content=_payload(exc.code, exc.message, exc.details),
        headers=headers or None,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Surface which parameter failed and why - a bare "422" is useless to a client.
    problems = [
        {
            "location": " -> ".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg", "invalid value"),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    logger.info("request_validation_failed", path=request.url.path, problems=problems)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_payload(
            "validation_error",
            "One or more request parameters are invalid.",
            {"problems": problems},
        ),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload("http_error", str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the full traceback server-side, return an opaque message to the client:
    # internal details (paths, SQL, driver messages) must not leak.
    logger.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    message = "An unexpected error occurred."
    if not get_settings().is_production:
        message = f"{type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_payload("internal_error", message),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SotAnalyzerError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
