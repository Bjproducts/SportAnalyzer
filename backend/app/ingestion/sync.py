"""Quota-aware orchestration for incremental multi-league imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import COMPLETED_FIXTURE_STATUSES
from app.ingestion.leagues import TrackedLeague
from app.ingestion.provider import FootballDataProvider, ProviderQuota
from app.ingestion.service import IngestionService
from app.models import Competition, Fixture, PlayerFixtureStats, Season


@dataclass(frozen=True, slots=True)
class LeagueSyncSummary:
    slug: str
    provider_id: int
    name: str
    fixture_job_id: int | None
    fixtures_processed: int
    fixtures_created: int
    fixtures_updated: int
    statistic_fixtures_requested: int
    statistic_jobs: int
    statistic_rows_created: int
    statistic_rows_updated: int
    statistic_rows_failed: int


@dataclass(frozen=True, slots=True)
class LeagueSyncReport:
    season: int
    leagues: tuple[LeagueSyncSummary, ...]
    quota: ProviderQuota | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


async def sync_leagues(
    session: AsyncSession,
    provider: FootballDataProvider,
    leagues: tuple[TrackedLeague, ...],
    *,
    season: int,
    max_stat_fixtures_per_league: int | None = 10,
    statistics_batch_size: int = 100,
    refresh_fixtures: bool = True,
) -> LeagueSyncReport:
    """Refresh fixtures, then import missing finished-match player statistics.

    One provider instance is deliberately shared across the whole run so its
    cooperative per-minute limiter applies across league and job boundaries.
    """
    if not 1850 <= season <= 2200:
        raise ValueError("season must be between 1850 and 2200")
    if max_stat_fixtures_per_league is not None and max_stat_fixtures_per_league < 0:
        raise ValueError("max_stat_fixtures_per_league cannot be negative")
    if not 1 <= statistics_batch_size <= 100:
        raise ValueError("statistics_batch_size must be between 1 and 100")

    service = IngestionService(session, provider, close_provider=False)
    summaries: list[LeagueSyncSummary] = []
    try:
        for league in leagues:
            fixture_job = (
                await service.ingest_fixtures(league.provider_id, season)
                if refresh_fixtures
                else None
            )
            fixture_ids = await _missing_stat_fixture_ids(
                session,
                provider_competition_id=league.provider_id,
                season=season,
                limit=max_stat_fixtures_per_league,
            )
            statistic_jobs = []
            for start in range(0, len(fixture_ids), statistics_batch_size):
                statistic_jobs.append(
                    await service.ingest_player_statistics(
                        fixture_ids[start : start + statistics_batch_size]
                    )
                )
            summaries.append(
                LeagueSyncSummary(
                    slug=league.slug,
                    provider_id=league.provider_id,
                    name=league.name,
                    fixture_job_id=fixture_job.id if fixture_job is not None else None,
                    fixtures_processed=fixture_job.records_processed if fixture_job else 0,
                    fixtures_created=fixture_job.records_created if fixture_job else 0,
                    fixtures_updated=fixture_job.records_updated if fixture_job else 0,
                    statistic_fixtures_requested=len(fixture_ids),
                    statistic_jobs=len(statistic_jobs),
                    statistic_rows_created=sum(job.records_created for job in statistic_jobs),
                    statistic_rows_updated=sum(job.records_updated for job in statistic_jobs),
                    statistic_rows_failed=sum(job.records_failed for job in statistic_jobs),
                )
            )
        return LeagueSyncReport(season=season, leagues=tuple(summaries), quota=provider.quota)
    finally:
        await provider.aclose()


async def _missing_stat_fixture_ids(
    session: AsyncSession,
    *,
    provider_competition_id: int,
    season: int,
    limit: int | None,
) -> list[int]:
    has_statistics = (
        select(PlayerFixtureStats.id).where(PlayerFixtureStats.fixture_id == Fixture.id).exists()
    )
    statement = (
        select(Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(Season, Fixture.season_id == Season.id)
        .where(
            Competition.provider_competition_id == provider_competition_id,
            Season.season_year == season,
            Fixture.status.in_(tuple(COMPLETED_FIXTURE_STATUSES)),
            ~has_statistics,
        )
        .order_by(Fixture.fixture_date.desc(), Fixture.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list((await session.scalars(statement)).all())
