"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.logging import get_logger
from app.database import Database, get_database

logger = get_logger(__name__)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    database: Database = get_database()
    async with database.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_admin_token(
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Guard for administrative ingestion routes.

    Uses a constant-time comparison so the token cannot be recovered by timing
    the response.  Refuses to authorise anything when no token is configured -
    an unset token must fail closed, never open.
    """
    expected = settings.admin_api_token.get_secret_value()
    if not expected:
        logger.error("admin_token_not_configured")
        raise UnauthorizedError(
            "Administrative routes are disabled because ADMIN_API_TOKEN is not set."
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        # Never log the supplied value - it may be a near-miss of the real token.
        logger.warning("admin_token_rejected")
        raise UnauthorizedError("A valid X-Admin-Token header is required.")


AdminGuard = Depends(require_admin_token)
