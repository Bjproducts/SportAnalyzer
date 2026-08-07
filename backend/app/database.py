"""Async database engine, session factory and declarative base.

The engine is wrapped in a small :class:`Database` object rather than created
at import time.  Importing ``app.database`` must never open a socket - that
keeps unit tests (and ``--help`` style CLI invocations) fast and offline, and
lets tests swap in a SQLite engine without monkeypatching module globals.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Explicit naming convention so Alembic autogenerate produces stable,
# human-readable constraint names instead of database-assigned ones.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """``created_at`` / ``updated_at`` columns, always stored in UTC.

    Defaults are applied database-side (``now()``) so that rows written by
    migrations or raw SQL get correct timestamps too, not just ORM inserts.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Database:
    """Owns one async engine and its session factory."""

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        connect_args: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        kwargs: dict[str, Any] = {
            "echo": echo,
            "pool_pre_ping": True,
            "future": True,
            "connect_args": connect_args or {},
        }
        # SQLite (used by tests) has no connection pool sizing knobs.
        if not url.startswith("sqlite"):
            kwargs["pool_size"] = pool_size
            kwargs["max_overflow"] = max_overflow

        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session, rolling back on any exception."""
        session = self.session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Yield a session wrapped in a single transaction.

        Used by ingestion so that a partially-applied import can never be
        committed: either every row of the batch lands or none of it does.
        """
        async with self.session() as session, session.begin():
            yield session

    async def connect(self) -> AsyncConnection:
        return await self.engine.connect()

    async def healthcheck(self) -> bool:
        """Return True when the database answers a trivial query."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("database_healthcheck_failed", error=str(exc))
            return False

    async def dispose(self) -> None:
        await self.engine.dispose()


_database: Database | None = None


def init_database(settings: Settings | None = None) -> Database:
    """Create (once) and return the process-wide :class:`Database`."""
    global _database
    if _database is None:
        cfg = settings or get_settings()
        _database = Database(
            cfg.sqlalchemy_database_uri,
            echo=cfg.db_echo,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
        )
        # Host/port only - the DSN contains the password and must not be logged.
        logger.info(
            "database_initialised",
            host=cfg.postgres_host,
            port=cfg.postgres_port,
            database=cfg.postgres_db,
        )
    return _database


def get_database() -> Database:
    """Return the initialised database, creating it on first use."""
    return init_database()


async def close_database() -> None:
    """Dispose the engine and clear the singleton (used on shutdown/in tests)."""
    global _database
    if _database is not None:
        await _database.dispose()
        _database = None
