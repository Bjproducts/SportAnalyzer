"""Alembic migration environment.

The database URL is resolved from application settings rather than
``alembic.ini`` so that the password is never written to a committed file.

Migrations run synchronously.  The ``psycopg`` dialect backs both
``create_engine`` and ``create_async_engine``, so no async plumbing is needed
here even though the application itself is async.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.core.migrations import make_include_object
from app.database import Base

# Importing the package registers every model on Base.metadata. Without this
# autogenerate would produce an empty - and silently destructive - migration.
import app.models  # noqa: F401  isort:skip

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Async drivers cannot be used by Alembic's synchronous engine. Map them to
#: their sync equivalents so `ALEMBIC_DATABASE_URL=sqlite+aiosqlite://...`
#: (which is what the test suite has to hand) still works.
_ASYNC_TO_SYNC_DRIVER = {
    "sqlite+aiosqlite": "sqlite",
    "postgresql+asyncpg": "postgresql+psycopg",
    "mysql+aiomysql": "mysql+pymysql",
}


def get_database_url() -> str:
    """Resolve the migration target URL.

    ``ALEMBIC_DATABASE_URL`` wins when set, which lets tests point migrations
    at a temporary database without touching application settings.
    """
    url = os.getenv("ALEMBIC_DATABASE_URL") or get_settings().sqlalchemy_database_uri
    for async_prefix, sync_prefix in _ASYNC_TO_SYNC_DRIVER.items():
        if url.startswith(f"{async_prefix}:"):
            return url.replace(f"{async_prefix}:", f"{sync_prefix}:", 1)
    return url


#: Excludes Alembic's version table and the CHECK constraints that SQLAlchemy
#: generates from Enum column types. See app.core.migrations for why.
include_object = make_include_object(target_metadata)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade --sql``)."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            # Deliberately off. PostgreSQL is the only real migration target;
            # SQLite appears solely in tests, which create the schema fresh and
            # never ALTER it. Batch mode would emit SQLite-shaped scripts even
            # when autogenerating against a scratch SQLite database.
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
