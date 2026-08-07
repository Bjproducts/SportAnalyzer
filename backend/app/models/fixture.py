"""Fixture model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import COMPLETED_FIXTURE_STATUSES, FixtureStatus
from app.database import Base, TimestampMixin
from app.models.types import enum_column

if TYPE_CHECKING:
    from app.models.competition import Competition, Season
    from app.models.player_fixture_stats import PlayerFixtureStats
    from app.models.team import Team


class Fixture(Base, TimestampMixin):
    """A single match.

    ``fixture_date`` is stored timezone-aware and is always UTC. Conversion to
    a local timezone happens only at the display edge.
    """

    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint("provider_fixture_id", name=None),
        CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
        CheckConstraint("home_score IS NULL OR home_score >= 0", name="home_score_non_negative"),
        CheckConstraint("away_score IS NULL OR away_score >= 0", name="away_score_non_negative"),
        # Newest-first listings for a competition/season, the default sort.
        Index("ix_fixtures_competition_season_date", "competition_id", "season_id", "fixture_date"),
        Index("ix_fixtures_fixture_date", "fixture_date"),
        Index("ix_fixtures_home_team_id_fixture_date", "home_team_id", "fixture_date"),
        Index("ix_fixtures_away_team_id_fixture_date", "away_team_id", "fixture_date"),
        Index("ix_fixtures_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_fixture_id: Mapped[int] = mapped_column(Integer, nullable=False)

    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    fixture_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    home_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
    )
    away_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
    )

    #: NULL until the match has been played.
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[FixtureStatus] = mapped_column(
        enum_column(FixtureStatus), nullable=False, default=FixtureStatus.SCHEDULED
    )
    venue: Mapped[str | None] = mapped_column(String(200))
    round: Mapped[str | None] = mapped_column(String(100))

    #: When this row was last refreshed from the provider. Used to decide what
    #: needs re-fetching and to show data freshness in the UI.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    competition: Mapped[Competition] = relationship(back_populates="fixtures")
    season: Mapped[Season] = relationship(back_populates="fixtures")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    player_stats: Mapped[list[PlayerFixtureStats]] = relationship(
        back_populates="fixture", cascade="all, delete-orphan"
    )

    @property
    def is_completed(self) -> bool:
        """True when the match finished and its statistics are final."""
        return self.status in COMPLETED_FIXTURE_STATUSES

    def opponent_id_for(self, team_id: int) -> int:
        """Return the other team's id.

        Raises ``ValueError`` when ``team_id`` did not play in this fixture -
        silently returning one of the two ids would corrupt opponent splits.
        """
        if team_id == self.home_team_id:
            return self.away_team_id
        if team_id == self.away_team_id:
            return self.home_team_id
        raise ValueError(
            f"Team {team_id} did not play in fixture {self.id} "
            f"({self.home_team_id} vs {self.away_team_id})."
        )

    def is_home_for(self, team_id: int) -> bool:
        """True when ``team_id`` was the home side."""
        if team_id not in (self.home_team_id, self.away_team_id):
            raise ValueError(f"Team {team_id} did not play in fixture {self.id}.")
        return team_id == self.home_team_id

    def __repr__(self) -> str:
        return (
            f"<Fixture id={self.id} {self.home_team_id} v {self.away_team_id} {self.fixture_date}>"
        )
