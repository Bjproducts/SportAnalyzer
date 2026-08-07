"""Application exception hierarchy.

Domain code raises these; the API layer translates them into HTTP responses in
one place (``app.api.errors``).  Services therefore never import ``fastapi``.
"""

from __future__ import annotations

from typing import Any


class SotAnalyzerError(Exception):
    """Base class for every error this application raises deliberately."""

    #: Stable machine-readable code returned to clients.
    code: str = "internal_error"
    #: Default HTTP status used by the API translation layer.
    http_status: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(SotAnalyzerError):
    """A requested entity does not exist."""

    code = "not_found"
    http_status = 404

    def __init__(self, entity: str, identifier: object) -> None:
        super().__init__(
            f"{entity} with id {identifier!r} was not found.",
            details={"entity": entity, "id": str(identifier)},
        )


class ValidationError(SotAnalyzerError):
    """Input passed schema validation but is invalid in context."""

    code = "validation_error"
    http_status = 422


class ConflictError(SotAnalyzerError):
    """The operation conflicts with existing state (e.g. duplicate record)."""

    code = "conflict"
    http_status = 409


class UnauthorizedError(SotAnalyzerError):
    """Missing or invalid credentials."""

    code = "unauthorized"
    http_status = 401


class ProviderError(SotAnalyzerError):
    """The upstream football-data provider failed."""

    code = "provider_error"
    http_status = 502

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "provider": provider,
                "upstream_status": status_code,
                "retryable": retryable,
                **(details or {}),
            },
        )
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class ProviderRateLimitError(ProviderError):
    """The provider rejected the call because a rate limit was exceeded."""

    code = "provider_rate_limited"
    http_status = 429

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            status_code=429,
            retryable=True,
            details={"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class IngestionError(SotAnalyzerError):
    """An ingestion job failed and the reason must be recorded, not swallowed."""

    code = "ingestion_error"
    http_status = 500
