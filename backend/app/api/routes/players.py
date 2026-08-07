"""Player search, match history and shots-on-target analytics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import SessionDep
from app.repositories.players import PlayerMatchQuery
from app.schemas.players import (
    AnalysisFilterParams,
    MatchListParams,
    PlayerDetail,
    PlayerMatchesResponse,
    PlayerSearchParams,
    PlayerSearchResponse,
    PlayerSotSummaryResponse,
    PlayerSplitsResponse,
    PlayerStreaksResponse,
    SplitParams,
    StreakParams,
)
from app.schemas.teams import ComparisonParams, PlayerComparisonResponse
from app.services.player_analytics import PlayerAnalyticsService
from app.services.team_analytics import TeamAnalyticsService

router = APIRouter(prefix="/players", tags=["players"])
PlayerId = Annotated[int, Path(gt=0, description="Internal player identifier")]


def _match_query(
    params: AnalysisFilterParams,
    *,
    minimum_sot: int | None = None,
) -> PlayerMatchQuery:
    return PlayerMatchQuery(
        starts_only=params.starts_only,
        venue=params.venue,
        competition_id=params.competition_id,
        season=params.season,
        last_n=params.last_n,
        date_from=params.date_from,
        date_to=params.date_to,
        minimum_minutes=params.minimum_minutes,
        opponent_id=params.opponent_id,
        team_id=params.team_id,
        position=params.position,
        minimum_sot=minimum_sot,
    )


@router.get(
    "",
    response_model=PlayerSearchResponse,
    summary="Search players by full or common name",
)
async def search_players(
    session: SessionDep,
    params: Annotated[PlayerSearchParams, Query()],
) -> PlayerSearchResponse:
    return await PlayerAnalyticsService(session).search_players(
        params.q,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/compare",
    response_model=PlayerComparisonResponse,
    summary="Compare two to four players with sample sizes",
)
async def compare_players(
    session: SessionDep,
    params: Annotated[ComparisonParams, Query()],
) -> PlayerComparisonResponse:
    return await TeamAnalyticsService(session).compare_players(
        params.player_ids,
        _match_query(params),
    )


@router.get(
    "/{player_id}",
    response_model=PlayerDetail,
    summary="Get one player's profile",
)
async def get_player(player_id: PlayerId, session: SessionDep) -> PlayerDetail:
    return await PlayerAnalyticsService(session).get_player(player_id)


@router.get(
    "/{player_id}/matches",
    response_model=PlayerMatchesResponse,
    summary="List a player's filtered match history",
)
async def get_player_matches(
    player_id: PlayerId,
    session: SessionDep,
    params: Annotated[MatchListParams, Query()],
) -> PlayerMatchesResponse:
    return await PlayerAnalyticsService(session).get_matches(
        player_id,
        _match_query(params, minimum_sot=params.sot_threshold),
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{player_id}/sot-summary",
    response_model=PlayerSotSummaryResponse,
    summary="Calculate a player's SOT summary and recent form",
)
async def get_player_sot_summary(
    player_id: PlayerId,
    session: SessionDep,
    params: Annotated[AnalysisFilterParams, Query()],
) -> PlayerSotSummaryResponse:
    return await PlayerAnalyticsService(session).get_summary(player_id, _match_query(params))


@router.get(
    "/{player_id}/splits",
    response_model=PlayerSplitsResponse,
    summary="Calculate venue, competition, season and opponent splits",
)
async def get_player_splits(
    player_id: PlayerId,
    session: SessionDep,
    params: Annotated[SplitParams, Query()],
) -> PlayerSplitsResponse:
    return await PlayerAnalyticsService(session).get_splits(
        player_id,
        _match_query(params),
        threshold=params.threshold,
        minimum_starts=params.minimum_starts,
    )


@router.get(
    "/{player_id}/streaks",
    response_model=PlayerStreaksResponse,
    summary="Calculate current and longest SOT streaks",
)
async def get_player_streaks(
    player_id: PlayerId,
    session: SessionDep,
    params: Annotated[StreakParams, Query()],
) -> PlayerStreaksResponse:
    return await PlayerAnalyticsService(session).get_streaks(
        player_id,
        _match_query(params),
        threshold=params.threshold,
    )
