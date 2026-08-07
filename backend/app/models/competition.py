"""Competition and season models."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NON_COMPETITIVE_TYPES, CompetitionType
from app.database import Base, TimestampMixin
from app.models.types import enum_column

if TYPE_CHECKING:
    from app.models.fixture import Fixture


class Competition(Base, TimestampMixin):
    """A competition (league, cup, continental tournament).

    ``provider_competition_id`` is unique: this schema assumes a single
    configured data provider per deployment. Supporting several simultaneously
    would require a composite ``(provider, provider_id)`` key.
    """

    __tablename__ = "competitions"
    __table_args__ = (
        UniqueConstraint("provider_competition_id", name=None),
        Index("ix_competitions_country_type", "country", "competition_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_competition_id: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100))
    competition_type: Mapped[CompetitionType] = mapped_column(
        enum_column(CompetitionType),
        nullable=False,
        default=CompetitionType.LEAGUE,
    )
    logo_url: Mapped[str | None] = mapped_column(String(500))

    #: Denormalised from ``competition_type`` at write time so that the default
    #: "competitive matches only" filter is a single indexed predicate rather
    #: than a NOT IN list that has to change whenever a type is added.
    is_competitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    seasons: Mapped[list[Season]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    fixtures: Mapped[list[Fixture]] = relationship(back_populates="competition")

    @staticmethod
    def derive_is_competitive(competition_type: CompetitionType) -> bool:
        """Single definition of what counts as a competitive competition."""
        return competition_type not in NON_COMPETITIVE_TYPES

    def __repr__(self) -> str:
        return f"<Competition id={self.id} name={self.name!r}>"


class Season(Base, TimestampMixin):
    """One season of one competition."""

    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("competition_id", "season_year", name=None),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="end_after_start",
        ),
        CheckConstraint("season_year BETWEEN 1850 AND 2200", name="season_year_range"),
        Index("ix_seasons_is_current", "is_current"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Starting calendar year. A 2024/25 season is stored as 2024.
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Human label, e.g. "2024/25" for split-year seasons or "2024" otherwise.
    label: Mapped[str] = mapped_column(String(20), nullable=False)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    competition: Mapped[Competition] = relationship(back_populates="seasons")
    fixtures: Mapped[list[Fixture]] = relationship(back_populates="season")

    def __repr__(self) -> str:
        return f"<Season id={self.id} competition_id={self.competition_id} {self.label}>"
