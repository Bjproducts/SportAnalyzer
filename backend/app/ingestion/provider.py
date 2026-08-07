"""Provider-neutral football data contracts used by every adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from app.core.enums import DataQualityStatus, FixtureStatus


@dataclass(frozen=True, slots=True)
class ProviderCompetition:
    id: int
    name: str
    country: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderTeam:
    id: int
    name: str
    short_name: str | None = None
    country: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderPlayer:
    id: int
    full_name: str
    common_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    position: str | None = None
    preferred_foot: str | None = None
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderFixture:
    id: int
    competition: ProviderCompetition
    season_year: int
    season_label: str
    fixture_date: datetime
    home_team: ProviderTeam
    away_team: ProviderTeam
    status: FixtureStatus
    home_score: int | None = None
    away_score: int | None = None
    venue: str | None = None
    round: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderPlayerStat:
    player: ProviderPlayer
    team_id: int
    opponent_id: int
    home: bool
    started: bool
    substitute_appearance: bool
    minutes_played: int | None = None
    position: str | None = None
    shirt_number: int | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    goals: int | None = None
    assists: int | None = None
    key_passes: int | None = None
    touches: int | None = None
    rating: float | None = None
    team_shots: int | None = None
    team_shots_on_target: int | None = None
    data_quality_status: DataQualityStatus = DataQualityStatus.COMPLETE
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderQuota:
    daily_limit: int | None = None
    daily_remaining: int | None = None
    minute_limit: int | None = None
    minute_remaining: int | None = None


class FootballDataProvider(Protocol):
    name: str

    @property
    def quota(self) -> ProviderQuota | None: ...

    async def search_players(self, query: str) -> list[ProviderPlayer]: ...

    async def get_fixtures(self, competition_id: int, season: int) -> list[ProviderFixture]: ...

    async def get_lineups(self, fixture_id: int) -> list[dict[str, Any]]: ...

    async def get_player_fixture_statistics(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> list[ProviderPlayerStat]: ...

    async def aclose(self) -> None: ...
