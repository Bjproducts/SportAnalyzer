"""Shared pytest fixtures.

Tests must run without Postgres, without Docker and without network access.
The database-backed fixtures therefore use in-memory SQLite via aiosqlite.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

# Settings are read at import time by several modules, so the environment must
# be shaped before `app.*` is imported anywhere in the test session.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_API_TOKEN", "test-admin-token")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("FOOTBALL_PROVIDER", "fake")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.database import Base, Database

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    """A fresh in-memory database with the full schema created."""
    db = Database.__new__(Database)
    db.url = TEST_DB_URL
    # StaticPool keeps every connection pointed at the same in-memory database;
    # without it each connection would get its own empty one.
    db.engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # SQLite ignores foreign keys unless asked. Without this, tests would pass
    # against referential integrity that PostgreSQL would actually enforce.
    @event.listens_for(db.engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    db.session_factory = async_sessionmaker(bind=db.engine, expire_on_commit=False, autoflush=False)

    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
async def session(database: Database):
    """A session bound to the in-memory test database."""
    async with database.session() as s:
        yield s


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Keep settings mutations in one test from leaking into the next."""
    yield
    get_settings.cache_clear()
