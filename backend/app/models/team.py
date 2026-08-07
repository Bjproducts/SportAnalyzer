"""Team model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.text import normalize_name
from app.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.player import Player


class Team(Base, TimestampMixin):
    """A club or national team."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("provider_team_id", name=None),
        # Prefix search on the folded name, e.g. WHERE search_name LIKE 'arsen%'.
        Index("ix_teams_search_name", "search_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(60))
    country: Mapped[str | None] = mapped_column(String(100))
    logo_url: Mapped[str | None] = mapped_column(String(500))

    #: Lowercase, accent-folded form of ``name``. Populated via
    #: :meth:`apply_search_name` so search works for "besiktas" -> "Beşiktaş".
    search_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")

    players: Mapped[list[Player]] = relationship(back_populates="current_team")

    def apply_search_name(self) -> None:
        """Recompute the folded search key from the display name."""
        self.search_name = normalize_name(self.name)

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"
