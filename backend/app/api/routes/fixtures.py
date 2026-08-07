"""Fixture lookup endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Path, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import SessionDep
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Fixture
from app.schemas.fixtures import FixtureResponse, FixturesResponse
from app.schemas.players import PaginationMeta
from app.schemas.previews import DailyFixtureAnalysisResponse
from app.services.fixture_previews import FixturePreviewService

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def _options() -> tuple[Any, ...]:
    return (
        joinedload(Fixture.competition),
        joinedload(Fixture.season),
        joinedload(Fixture.home_team),
        joinedload(Fixture.away_team),
    )


@router.get("/upcoming-analysis", response_model=DailyFixtureAnalysisResponse)
async def upcoming_fixture_analysis(
    session: SessionDep,
    analysis_date: Annotated[date | None, Query(alias="date")] = None,
    window: Annotated[int, Query(ge=5, le=20)] = 5,
    candidates_per_team: Annotated[int, Query(ge=1, le=5)] = 5,
) -> DailyFixtureAnalysisResponse:
    """Rank both squads for every scheduled fixture on one UTC date."""
    if window not in (5, 10, 20):
        raise ValidationError("window must be 5, 10 or 20")
    selected_date = analysis_date or datetime.now(UTC).date()
    return await FixturePreviewService(session).daily(
        selected_date,
        window=cast(Literal[5, 10, 20], window),
        candidates_per_team=candidates_per_team,
    )


@router.get("", response_model=FixturesResponse)
async def list_fixtures(
    session: SessionDep,
    competition_id: Annotated[int | None, Query(gt=0)] = None,
    season: Annotated[int | None, Query(ge=1850, le=2200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FixturesResponse:
    statement = select(Fixture).options(*_options())
    count_statement = select(func.count(Fixture.id))
    if competition_id is not None:
        statement = statement.where(Fixture.competition_id == competition_id)
        count_statement = count_statement.where(Fixture.competition_id == competition_id)
    if season is not None:
        statement = statement.join(Fixture.season).where(Fixture.season.has(season_year=season))
        count_statement = count_statement.where(Fixture.season.has(season_year=season))
    total = int(await session.scalar(count_statement) or 0)
    fixtures = list(
        (
            await session.scalars(
                statement.order_by(Fixture.fixture_date.desc(), Fixture.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .unique()
        .all()
    )
    return FixturesResponse(
        items=[FixtureResponse.model_validate(item) for item in fixtures],
        pagination=PaginationMeta.build(page=page, page_size=page_size, total=total),
    )


@router.get("/{fixture_id}", response_model=FixtureResponse)
async def get_fixture(
    fixture_id: Annotated[int, Path(gt=0)], session: SessionDep
) -> FixtureResponse:
    fixture = await session.scalar(
        select(Fixture).options(*_options()).where(Fixture.id == fixture_id)
    )
    if fixture is None:
        raise NotFoundError("Fixture", fixture_id)
    return FixtureResponse.model_validate(fixture)
