"""Player model."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PositionGroup, PreferredFoot
from app.core.text import normalize_name
from app.database import Base, TimestampMixin
from app.models.types import enum_column

if TYPE_CHECKING:
    from app.models.player_fixture_stats import PlayerFixtureStats
    from app.models.team import Team


class Player(Base, TimestampMixin):
    """A football player."""

    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("provider_player_id", name=None),
        # Drives player search: WHERE search_name LIKE 'harry k%'.
        Index("ix_players_search_name", "search_name"),
        Index("ix_players_search_common_name", "search_common_name"),
        Index("ix_players_current_team_id_position_group", "current_team_id", "position_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_player_id: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Full registered name, e.g. "Harry Edward Kane".
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Name normally used in broadcast/press, e.g. "Harry Kane".
    common_name: Mapped[str | None] = mapped_column(String(150))

    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(100))

    #: Provider's own position label, kept verbatim for auditing.
    primary_position: Mapped[str | None] = mapped_column(String(60))
    #: Normalised grouping used by filters and comparisons.
    position_group: Mapped[PositionGroup] = mapped_column(
        enum_column(PositionGroup), nullable=False, default=PositionGroup.UNKNOWN
    )
    preferred_foot: Mapped[PreferredFoot] = mapped_column(
        enum_column(PreferredFoot), nullable=False, default=PreferredFoot.UNKNOWN
    )

    current_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    photo_url: Mapped[str | None] = mapped_column(String(500))

    #: Folded search keys, maintained by :meth:`apply_search_names`.
    search_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    search_common_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")

    current_team: Mapped[Team | None] = relationship(back_populates="players")
    fixture_stats: Mapped[list[PlayerFixtureStats]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        """Preferred name for display: the common name when one is known."""
        return self.common_name or self.full_name

    def apply_search_names(self) -> None:
        """Recompute both folded search keys from the display names."""
        self.search_name = normalize_name(self.full_name)
        self.search_common_name = normalize_name(self.common_name or self.full_name)

    def __repr__(self) -> str:
        return f"<Player id={self.id} name={self.display_name!r}>"
