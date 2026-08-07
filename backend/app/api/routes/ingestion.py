"""Protected administrative ingestion endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import SessionDep, SettingsDep, require_admin_token
from app.ingestion.factory import create_provider
from app.ingestion.leagues import TRACKED_LEAGUES
from app.ingestion.service import IngestionService
from app.ingestion.sports_api_leagues import SPORTS_API_PRO_LEAGUES
from app.models import IngestionJob
from app.schemas.ingestion import (
    FixtureIngestionRequest,
    IngestionJobResponse,
    IngestionJobsResponse,
    PlayerStatisticsIngestionRequest,
    TrackedLeagueResponse,
    TrackedLeaguesResponse,
)

router = APIRouter(
    prefix="/admin/ingestion",
    tags=["admin ingestion"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("/leagues", response_model=TrackedLeaguesResponse)
async def list_tracked_leagues(settings: SettingsDep) -> TrackedLeaguesResponse:
    leagues = (
        SPORTS_API_PRO_LEAGUES
        if settings.football_provider.strip().casefold() == "sportsapipro"
        else TRACKED_LEAGUES
    )
    return TrackedLeaguesResponse(
        items=[
            TrackedLeagueResponse(
                slug=league.slug,
                provider_id=league.provider_id,
                name=league.name,
                country=league.country,
                calendar_year_season=league.calendar_year_season,
            )
            for league in leagues
        ]
    )


@router.post("/fixtures", response_model=IngestionJobResponse)
async def ingest_fixtures(
    request: FixtureIngestionRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> IngestionJobResponse:
    job = await IngestionService(session, create_provider(settings)).ingest_fixtures(
        request.provider_competition_id,
        request.season,
    )
    return IngestionJobResponse.model_validate(job)


@router.post("/player-statistics", response_model=IngestionJobResponse)
async def ingest_player_statistics(
    request: PlayerStatisticsIngestionRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> IngestionJobResponse:
    job = await IngestionService(session, create_provider(settings)).ingest_player_statistics(
        request.fixture_ids
    )
    return IngestionJobResponse.model_validate(job)


@router.get("/jobs", response_model=IngestionJobsResponse)
async def list_ingestion_jobs(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> IngestionJobsResponse:
    total = int(await session.scalar(select(func.count(IngestionJob.id))) or 0)
    statement = (
        select(IngestionJob)
        .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    jobs = list((await session.scalars(statement)).all())
    return IngestionJobsResponse(
        items=[IngestionJobResponse.model_validate(job) for job in jobs],
        total=total,
    )
