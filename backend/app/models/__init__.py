"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata``, which is
what Alembic autogenerate and ``create_all`` rely on.  Any new model must be
imported here or it will be silently missing from generated migrations.
"""

from __future__ import annotations

from app.models.competition import Competition, Season
from app.models.fixture import Fixture
from app.models.ingestion_job import IngestionJob
from app.models.player import Player
from app.models.player_fixture_stats import PlayerFixtureStats
from app.models.team import Team

__all__ = [
    "Competition",
    "Fixture",
    "IngestionJob",
    "Player",
    "PlayerFixtureStats",
    "Season",
    "Team",
]
