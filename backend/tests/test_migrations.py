"""Alembic migration tests.

The important guarantee here is that the migration chain and the ORM models
cannot silently diverge.  Adding a column to a model and forgetting to generate
a migration is the single most common way a working development database and a
broken production one come apart, and it is invisible to every other test
because the rest of the suite builds its schema with ``create_all``.

These run against SQLite, so PostgreSQL-only details (JSONB, SERIAL) are not
exercised.  Structure - tables, columns, nullability, indexes and unique
constraints - is.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.migrations import make_include_object
from app.database import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TABLES = {
    "competitions",
    "seasons",
    "teams",
    "players",
    "fixtures",
    "player_fixture_stats",
    "ingestion_jobs",
}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def migrated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply every migration to a fresh SQLite file and return its URL."""
    db_path = tmp_path / "migrated.db"
    # as_posix() keeps Windows backslashes out of the SQLite URL.
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)

    command.upgrade(_alembic_config(url), "head")
    return url


def test_migrations_create_every_expected_table(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert tables >= EXPECTED_TABLES
    assert "alembic_version" in tables


def test_migrations_match_the_models(migrated_database: str) -> None:
    """No drift between the migration chain and ``Base.metadata``.

    A non-empty diff means someone changed a model without generating a
    migration (or hand-edited one incorrectly). Regenerate with:
        alembic revision --autogenerate -m "describe the change"
    """
    engine = create_engine(migrated_database)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    # Server defaults are rendered per-dialect (now() vs
                    # CURRENT_TIMESTAMP), so comparing them across SQLite and
                    # the PostgreSQL-targeted migration is pure noise.
                    "compare_server_default": False,
                    # Same filter alembic/env.py uses, so the test cannot pass
                    # while a real autogenerate run would produce a diff.
                    "include_object": make_include_object(Base.metadata),
                },
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], "Schema drift between migrations and models:\n" + "\n".join(
        f"  - {d}" for d in differences
    )


def test_the_unique_constraint_required_by_the_spec_exists(migrated_database: str) -> None:
    """(fixture_id, player_id, team_id) must be unique after migrating."""
    engine = create_engine(migrated_database)
    try:
        inspector = inspect(engine)
        constraints = inspector.get_unique_constraints("player_fixture_stats")
    finally:
        engine.dispose()

    assert any(
        set(c["column_names"]) == {"fixture_id", "player_id", "team_id"} for c in constraints
    ), f"Expected a unique constraint on the fixture/player/team triple, found: {constraints}"


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("player_fixture_stats", {"player_id", "started", "home"}),
        ("player_fixture_stats", {"player_id", "shots_on_target"}),
        ("player_fixture_stats", {"team_id", "started"}),
        ("player_fixture_stats", {"opponent_id", "started"}),
        ("player_fixture_stats", {"fixture_id"}),
        ("fixtures", {"fixture_date"}),
        ("fixtures", {"competition_id"}),
    ],
)
def test_required_indexes_exist(migrated_database: str, table: str, columns: set[str]) -> None:
    engine = create_engine(migrated_database)
    try:
        indexes = inspect(engine).get_indexes(table)
    finally:
        engine.dispose()

    assert any(set(ix["column_names"]) == columns for ix in indexes), (
        f"No index on {sorted(columns)} in {table}. Present: "
        f"{[sorted(ix['column_names']) for ix in indexes]}"
    )


def test_downgrade_removes_every_table(migrated_database: str) -> None:
    """A reversible migration is what makes a bad deploy recoverable."""
    config = _alembic_config(migrated_database)
    command.downgrade(config, "base")

    engine = create_engine(migrated_database)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert not (EXPECTED_TABLES & tables), f"Tables survived downgrade: {EXPECTED_TABLES & tables}"
