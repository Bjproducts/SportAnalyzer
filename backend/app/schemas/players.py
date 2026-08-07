"""Pydantic contracts for Phase 4 player and analytics endpoints."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.math import safe_divide
from app.analytics.models import (
    FormWindow,
    MatchStatLine,
    MinutesProfile,
    RateResult,
    SotSummary,
    SplitEntry,
    StreakSummary,
    VenueSplits,
)
from app.analytics.rules import has_usable_sot, is_early_exit, meets_threshold
from app.core.enums import DataQualityStatus, PositionGroup, PreferredFoot, Venue
from app.models import Player


class ApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(ApiSchema):
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def build(cls, *, page: int, page_size: int, total: int) -> Self:
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )


class PlayerSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: Annotated[str | None, Field(min_length=2, max_length=100)] = None
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20

    @model_validator(mode="after")
    def strip_query(self) -> Self:
        if self.q is not None:
            self.q = self.q.strip()
            if len(self.q) < 2:
                raise ValueError("q must contain at least 2 non-whitespace characters")
        return self


class AnalysisFilterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_only: bool = True
    venue: Venue = Venue.ALL
    competition_id: Annotated[int | None, Field(gt=0)] = None
    season: Annotated[int | None, Field(ge=1850, le=2200)] = None
    last_n: Annotated[int | None, Field(ge=1, le=100)] = None
    date_from: date | None = None
    date_to: date | None = None
    minimum_minutes: Annotated[int | None, Field(ge=0, le=200)] = None
    opponent_id: Annotated[int | None, Field(gt=0)] = None
    team_id: Annotated[int | None, Field(gt=0)] = None
    position: Annotated[str | None, Field(min_length=1, max_length=60)] = None

    @model_validator(mode="after")
    def validate_range_and_position(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if self.position is not None:
            self.position = self.position.strip()
            if not self.position:
                raise ValueError("position must not be blank")
        return self


class MatchListParams(AnalysisFilterParams):
    sot_threshold: Annotated[int | None, Field(ge=0, le=20)] = None
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20


class SplitParams(AnalysisFilterParams):
    threshold: Annotated[int, Field(ge=1, le=20)] = 1
    minimum_starts: Annotated[int, Field(ge=1, le=100)] = 1


class StreakParams(AnalysisFilterParams):
    threshold: Annotated[int, Field(ge=1, le=20)] = 1


class TeamBrief(ApiSchema):
    id: int
    name: str
    short_name: str | None
    country: str | None
    logo_url: str | None


class PlayerListItem(ApiSchema):
    id: int
    display_name: str
    full_name: str
    common_name: str | None
    nationality: str | None
    primary_position: str | None
    position_group: PositionGroup
    photo_url: str | None
    current_team: TeamBrief | None


class PlayerDetail(PlayerListItem):
    date_of_birth: date | None
    preferred_foot: PreferredFoot


def player_list_item(player: Player) -> PlayerListItem:
    return PlayerListItem.model_validate(player)


def player_detail(player: Player) -> PlayerDetail:
    return PlayerDetail.model_validate(player)


class PlayerSearchResponse(ApiSchema):
    items: list[PlayerListItem]
    pagination: PaginationMeta


class CompetitionBrief(ApiSchema):
    id: int
    name: str


class SeasonBrief(ApiSchema):
    id: int
    label: str


class PlayerMatch(ApiSchema):
    fixture_id: int
    fixture_date: datetime
    competition: CompetitionBrief
    season: SeasonBrief
    team: TeamBrief
    opponent: TeamBrief
    venue: Venue
    started: bool
    substitute_appearance: bool
    minutes_played: int | None
    position: str | None
    shots: int | None
    shots_on_target: int | None
    goals: int | None
    assists: int | None
    team_shots: int | None
    team_shots_on_target: int | None
    player_share_of_team_sot: float | None
    one_plus_sot: bool | None
    two_plus_sot: bool | None
    early_exit: bool | None
    data_quality_status: DataQualityStatus

    @classmethod
    def from_line(cls, line: MatchStatLine) -> Self:
        usable = has_usable_sot(line.shots_on_target, line.data_quality_status)
        early_exit = line.early_exit
        if early_exit is None:
            early_exit = is_early_exit(
                started=line.started,
                minutes_played=line.minutes_played,
            )
        return cls(
            fixture_id=line.fixture_id,
            fixture_date=line.fixture_date,
            competition=CompetitionBrief(
                id=line.competition_id,
                name=line.competition_name or f"Competition {line.competition_id}",
            ),
            season=SeasonBrief(
                id=line.season_id,
                label=line.season_label or f"Season {line.season_id}",
            ),
            team=TeamBrief(
                id=line.team_id,
                name=line.team_name or f"Team {line.team_id}",
                short_name=None,
                country=None,
                logo_url=None,
            ),
            opponent=TeamBrief(
                id=line.opponent_id,
                name=line.opponent_name or f"Team {line.opponent_id}",
                short_name=None,
                country=None,
                logo_url=None,
            ),
            venue=Venue.HOME if line.home else Venue.AWAY,
            started=line.started,
            substitute_appearance=line.substitute_appearance,
            minutes_played=line.minutes_played,
            position=line.position,
            shots=line.shots,
            shots_on_target=line.shots_on_target if usable else None,
            goals=line.goals,
            assists=line.assists,
            team_shots=line.team_shots,
            team_shots_on_target=line.team_shots_on_target,
            player_share_of_team_sot=(
                safe_divide(line.shots_on_target, line.team_shots_on_target) if usable else None
            ),
            one_plus_sot=meets_threshold(line.shots_on_target, 1) if usable else None,
            two_plus_sot=meets_threshold(line.shots_on_target, 2) if usable else None,
            early_exit=early_exit,
            data_quality_status=line.data_quality_status,
        )


class PlayerMatchesResponse(ApiSchema):
    player: PlayerListItem
    items: list[PlayerMatch]
    pagination: PaginationMeta


class RateResponse(ApiSchema):
    successes: int
    valid: int
    failures: int
    missing: int
    percentage: float | None
    criterion: str
    description: str

    @classmethod
    def from_result(cls, rate: RateResult) -> Self:
        return cls(
            successes=rate.successes,
            valid=rate.valid,
            failures=rate.failures,
            missing=rate.missing,
            percentage=rate.percentage,
            criterion=rate.criterion,
            description=rate.describe(),
        )


class MinutesResponse(ApiSchema):
    starts_considered: int
    starts_with_known_minutes: int
    pct_at_least_60: float | None
    pct_at_least_80: float | None
    early_exits: int
    average_minutes_per_start: float | None
    total_minutes: int

    @classmethod
    def from_result(cls, minutes: MinutesProfile) -> Self:
        return cls.model_validate(minutes)


class SotSummaryResponse(ApiSchema):
    total_appearances: int
    total_starts: int
    substitute_appearances: int
    threshold_rates: dict[int, RateResponse]
    total_shots: int
    total_shots_on_target: int
    starts_missing_sot: int
    average_shots_per_start: float | None
    average_sot_per_start: float | None
    shots_per_90: float | None
    sot_per_90: float | None
    shot_accuracy: float | None
    team_sot_share: float | None
    minutes: MinutesResponse | None

    @classmethod
    def from_result(cls, summary: SotSummary) -> Self:
        return cls(
            total_appearances=summary.total_appearances,
            total_starts=summary.total_starts,
            substitute_appearances=summary.substitute_appearances,
            threshold_rates={
                threshold: RateResponse.from_result(rate)
                for threshold, rate in summary.threshold_rates.items()
            },
            total_shots=summary.total_shots,
            total_shots_on_target=summary.total_shots_on_target,
            starts_missing_sot=summary.starts_missing_sot,
            average_shots_per_start=summary.average_shots_per_start,
            average_sot_per_start=summary.average_sot_per_start,
            shots_per_90=summary.shots_per_90,
            sot_per_90=summary.sot_per_90,
            shot_accuracy=summary.shot_accuracy,
            team_sot_share=summary.team_sot_share,
            minutes=(MinutesResponse.from_result(summary.minutes) if summary.minutes else None),
        )


class FormWindowResponse(ApiSchema):
    window: int
    starts_available: int
    rate: RateResponse

    @classmethod
    def from_result(cls, form: FormWindow) -> Self:
        return cls(
            window=form.window,
            starts_available=form.starts_available,
            rate=RateResponse.from_result(form.rate),
        )


class PlayerSotSummaryResponse(ApiSchema):
    player: PlayerListItem
    summary: SotSummaryResponse
    recent_form: dict[int, FormWindowResponse]


class SplitEntryResponse(ApiSchema):
    key: str | int
    label: str
    rate: RateResponse
    average_sot: float | None
    average_shots: float | None
    total_starts: int

    @classmethod
    def from_result(cls, entry: SplitEntry) -> Self:
        return cls(
            key=entry.key,
            label=entry.label,
            rate=RateResponse.from_result(entry.rate),
            average_sot=entry.average_sot,
            average_shots=entry.average_shots,
            total_starts=entry.total_starts,
        )


class VenueSplitsResponse(ApiSchema):
    home: RateResponse
    away: RateResponse
    overall: RateResponse

    @classmethod
    def from_result(cls, splits: VenueSplits) -> Self:
        return cls(
            home=RateResponse.from_result(splits.home),
            away=RateResponse.from_result(splits.away),
            overall=RateResponse.from_result(splits.overall),
        )


class PlayerSplitsResponse(ApiSchema):
    player: PlayerListItem
    threshold: int
    venue: VenueSplitsResponse
    competitions: list[SplitEntryResponse]
    seasons: list[SplitEntryResponse]
    opponents: list[SplitEntryResponse]


class StreakResponse(ApiSchema):
    threshold: int
    current: int
    longest: int
    missing_in_window: int
    reliable: bool
    last_failure_date: datetime | None
    last_failure_fixture_id: int | None
    starts_since_last_failure: int
    never_failed: bool

    @classmethod
    def from_result(cls, streak: StreakSummary) -> Self:
        return cls(
            threshold=streak.threshold,
            current=streak.current,
            longest=streak.longest,
            missing_in_window=streak.missing_in_window,
            reliable=streak.is_reliable,
            last_failure_date=streak.last_failure_date,
            last_failure_fixture_id=streak.last_failure_fixture_id,
            starts_since_last_failure=streak.starts_since_last_failure,
            never_failed=streak.never_failed,
        )


class PlayerStreaksResponse(ApiSchema):
    player: PlayerListItem
    streak: StreakResponse
