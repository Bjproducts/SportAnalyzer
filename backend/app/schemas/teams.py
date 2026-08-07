"""Team, ranking and comparison API contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Venue
from app.schemas.players import (
    AnalysisFilterParams,
    PaginationMeta,
    PlayerListItem,
    RateResponse,
)


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None
    country: str | None
    logo_url: str | None


class TeamsResponse(BaseModel):
    items: list[TeamResponse]
    pagination: PaginationMeta


class TeamPlayersResponse(BaseModel):
    team: TeamResponse
    items: list[PlayerListItem]


class RankingParams(BaseModel):
    venue: Venue = Venue.ALL
    competition_id: Annotated[int | None, Field(gt=0)] = None
    season: Annotated[int | None, Field(ge=1850, le=2200)] = None
    minimum_starts: Annotated[int, Field(ge=1, le=100)] = 5
    threshold: Annotated[int, Field(ge=1, le=20)] = 1
    last_n: Annotated[int, Field(ge=5, le=20)] = 5
    limit: Annotated[int, Field(ge=1, le=100)] = 5

    @field_validator("last_n")
    @classmethod
    def validate_window(cls, value: int) -> int:
        if value not in (5, 10, 20):
            raise ValueError("last_n must be 5, 10 or 20")
        return value


class RankingEntry(BaseModel):
    rank: int
    eligible: bool
    player: PlayerListItem
    rate: RateResponse
    last_five_rate: float | None
    average_sot: float | None
    average_minutes: float | None
    current_streak: int
    sample_adjusted_rate: float | None


class TeamRankingsResponse(BaseModel):
    team: TeamResponse
    venue: Venue
    threshold: int
    minimum_starts: int
    last_n: int
    limit: int
    items: list[RankingEntry]


class ComparisonParams(AnalysisFilterParams):
    player_ids: Annotated[list[int], Field(min_length=2, max_length=4)]


class PlayerComparisonEntry(BaseModel):
    player: PlayerListItem
    one_plus_rate: RateResponse
    two_plus_rate: RateResponse
    average_sot: float | None
    sot_per_90: float | None
    home_rate: RateResponse
    away_rate: RateResponse
    last_five_rate: RateResponse
    last_ten_rate: RateResponse
    current_streak: int
    valid_starts: int


class PlayerComparisonResponse(BaseModel):
    items: list[PlayerComparisonEntry]
