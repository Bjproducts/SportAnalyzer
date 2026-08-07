"""Team squad and sample-adjusted SOT ranking endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import SessionDep
from app.schemas.teams import (
    RankingParams,
    TeamPlayersResponse,
    TeamRankingsResponse,
    TeamResponse,
    TeamsResponse,
)
from app.services.team_analytics import TeamAnalyticsService

router = APIRouter(prefix="/teams", tags=["teams"])
TeamId = Annotated[int, Path(gt=0)]


@router.get("", response_model=TeamsResponse)
async def list_teams(
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TeamsResponse:
    return await TeamAnalyticsService(session).list_teams(q, page=page, page_size=page_size)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: TeamId, session: SessionDep) -> TeamResponse:
    return await TeamAnalyticsService(session).get_team(team_id)


@router.get("/{team_id}/players", response_model=TeamPlayersResponse)
async def get_team_players(team_id: TeamId, session: SessionDep) -> TeamPlayersResponse:
    return await TeamAnalyticsService(session).get_players(team_id)


@router.get("/{team_id}/sot-rankings", response_model=TeamRankingsResponse)
async def get_team_rankings(
    team_id: TeamId,
    session: SessionDep,
    params: Annotated[RankingParams, Query()],
) -> TeamRankingsResponse:
    return await TeamAnalyticsService(session).rankings(
        team_id,
        venue=params.venue,
        competition_id=params.competition_id,
        season=params.season,
        minimum_starts=params.minimum_starts,
        threshold=params.threshold,
        last_n=params.last_n,
        limit=params.limit,
    )
