"""Fixture list/detail response contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import FixtureStatus
from app.schemas.players import CompetitionBrief, PaginationMeta, SeasonBrief, TeamBrief


class FixtureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fixture_date: datetime
    status: FixtureStatus
    home_score: int | None
    away_score: int | None
    venue: str | None
    round: str | None
    competition: CompetitionBrief
    season: SeasonBrief
    home_team: TeamBrief
    away_team: TeamBrief


class FixturesResponse(BaseModel):
    items: list[FixtureResponse]
    pagination: PaginationMeta
