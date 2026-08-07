"""Player-per-fixture statistics: the central table of the application."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.analytics.rules import DEFAULT_EARLY_EXIT_MINUTES, is_early_exit
from app.core.enums import DataQualityStatus
from app.database import Base, TimestampMixin
from app.models.types import JSONVariant, enum_column

if TYPE_CHECKING:
    from app.models.fixture import Fixture
    from app.models.player import Player
    from app.models.team import Team


class PlayerFixtureStats(Base, TimestampMixin):
    """One player's record in one fixture.

    The single most important property of this table is that ``shots_on_target``
    is **nullable**, and ``NULL`` means "the provider did not report a value" -
    never "zero".  Rate calculations exclude these rows from the denominator
    and report how many were excluded.
    """

    __tablename__ = "player_fixture_stats"
    __table_args__ = (
        # Required by the specification: prevents duplicate fixture-player rows
        # and gives ingestion a conflict target for idempotent upserts.
        UniqueConstraint("fixture_id", "player_id", "team_id", name=None),
        # --- Integrity -----------------------------------------------------
        CheckConstraint(
            "NOT (started AND substitute_appearance)",
            name="start_xor_substitute",
        ),
        CheckConstraint("team_id <> opponent_id", name="distinct_team_and_opponent"),
        CheckConstraint(
            "minutes_played IS NULL OR (minutes_played >= 0 AND minutes_played <= 200)",
            name="minutes_played_range",
        ),
        CheckConstraint("shots IS NULL OR shots >= 0", name="shots_non_negative"),
        CheckConstraint(
            "shots_on_target IS NULL OR shots_on_target >= 0",
            name="shots_on_target_non_negative",
        ),
        # NULL on either side makes this evaluate to NULL, which passes - so an
        # unknown SOT is still allowed alongside a known shot count.
        CheckConstraint(
            "shots IS NULL OR shots_on_target IS NULL OR shots_on_target <= shots",
            name="shots_on_target_within_shots",
        ),
        CheckConstraint("goals IS NULL OR goals >= 0", name="goals_non_negative"),
        CheckConstraint("assists IS NULL OR assists >= 0", name="assists_non_negative"),
        CheckConstraint(
            "team_shots_on_target IS NULL OR team_shots IS NULL "
            "OR team_shots_on_target <= team_shots",
            name="team_sot_within_team_shots",
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 10)",
            name="rating_range",
        ),
        # --- Indexes -------------------------------------------------------
        # The core query is "this player's starts, optionally at one venue",
        # so player_id leads and the two low-cardinality flags trail it.
        # Indexing `started` or `home` alone would be near-useless: each has
        # two values, so a standalone index cannot narrow the scan.
        Index("ix_player_fixture_stats_player_started_home", "player_id", "started", "home"),
        # Supports hit-rate scans and finding rows with unreported SOT.
        Index("ix_player_fixture_stats_player_sot", "player_id", "shots_on_target"),
        # Team squad listings and team-wide rankings.
        Index("ix_player_fixture_stats_team_started", "team_id", "started"),
        # Opponent splits / upcoming-matchup analysis.
        Index("ix_player_fixture_stats_opponent_started", "opponent_id", "started"),
        # Data-quality auditing: "show me everything that needs re-ingesting".
        Index("ix_player_fixture_stats_data_quality_status", "data_quality_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    fixture_id: Mapped[int] = mapped_column(
        ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
    )
    opponent_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Appearance --------------------------------------------------------
    home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    substitute_appearance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    minutes_played: Mapped[int | None] = mapped_column(Integer)
    #: Provider's position label for this match, stored verbatim.
    position: Mapped[str | None] = mapped_column(String(60))
    shirt_number: Mapped[int | None] = mapped_column(Integer)

    # --- Player statistics -------------------------------------------------
    shots: Mapped[int | None] = mapped_column(Integer)
    #: NULL means unreported. It does NOT mean zero. See the class docstring.
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    goals: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    key_passes: Mapped[int | None] = mapped_column(Integer)
    touches: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Numeric(4, 2))

    # --- Team context (for share-of-team calculations) ---------------------
    team_shots: Mapped[int | None] = mapped_column(Integer)
    team_shots_on_target: Mapped[int | None] = mapped_column(Integer)

    # --- Derived -----------------------------------------------------------
    #: Maintained by :meth:`apply_derived_fields`. NULL when the player started
    #: but minutes are unknown, i.e. the answer is genuinely unknowable.
    early_exit: Mapped[bool | None] = mapped_column(Boolean)

    # --- Provenance --------------------------------------------------------
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    data_quality_status: Mapped[DataQualityStatus] = mapped_column(
        enum_column(DataQualityStatus),
        nullable=False,
        default=DataQualityStatus.COMPLETE,
    )
    #: Original provider payload, kept for auditing and re-normalisation.
    provider_raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)

    fixture: Mapped[Fixture] = relationship(back_populates="player_stats")
    player: Mapped[Player] = relationship(back_populates="fixture_stats")
    team: Mapped[Team] = relationship(foreign_keys=[team_id])
    opponent: Mapped[Team] = relationship(foreign_keys=[opponent_id])

    def apply_derived_fields(self, early_exit_threshold: int = DEFAULT_EARLY_EXIT_MINUTES) -> None:
        """Recompute stored derived columns from the raw values.

        Called by ingestion before every insert or update. Uses the same
        :func:`app.analytics.rules.is_early_exit` the analytics engine uses, so
        the stored column and any recomputation always agree.
        """
        self.early_exit = is_early_exit(
            started=self.started,
            minutes_played=self.minutes_played,
            threshold=early_exit_threshold,
        )

    def __repr__(self) -> str:
        return (
            f"<PlayerFixtureStats fixture={self.fixture_id} player={self.player_id} "
            f"sot={self.shots_on_target} started={self.started}>"
        )
