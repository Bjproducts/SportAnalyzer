"""Import real, keyless historical SOT data from StatsBomb Open Data."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import SotAnalyzerError, ValidationError
from app.database import close_database, init_database
from app.ingestion.factory import create_provider
from app.ingestion.open_leagues import resolve_open_data_leagues
from app.ingestion.service import IngestionService
from app.ingestion.sync import _missing_stat_fixture_ids
from app.models import IngestionJob, PlayerFixtureStats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync selected historical leagues from free StatsBomb Open Data."
    )
    parser.add_argument(
        "--leagues",
        default="all",
        help="Comma-separated available slugs, or 'all' (default).",
    )
    parser.add_argument(
        "--max-stat-fixtures-per-league",
        type=int,
        default=5,
        help="Newest missing fixtures per league (default: 5; 0: fixtures only).",
    )
    parser.add_argument(
        "--all-missing-statistics",
        action="store_true",
        help="Import every missing match. This can download several gigabytes.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.football_provider.strip().casefold() != "statsbomb":
        raise ValueError("Set FOOTBALL_PROVIDER=statsbomb before an open-data sync.")
    if args.max_stat_fixtures_per_league < 0:
        raise ValueError("--max-stat-fixtures-per-league cannot be negative")
    leagues = resolve_open_data_leagues(args.leagues)
    limit = None if args.all_missing_statistics else args.max_stat_fixtures_per_league
    database = init_database(settings)
    provider = create_provider(settings)
    summaries: list[dict[str, object]] = []
    try:
        async with database.session() as session:
            await _ensure_open_data_database(session)
            service = IngestionService(session, provider, close_provider=False)
            for league in leagues:
                fixture_job = await service.ingest_fixtures(league.competition_id, league.season_id)
                fixture_ids = await _missing_stat_fixture_ids(
                    session,
                    provider_competition_id=league.competition_id,
                    season=league.season_year,
                    limit=limit,
                )
                stat_job = (
                    await service.ingest_player_statistics(fixture_ids) if fixture_ids else None
                )
                summaries.append(
                    {
                        **asdict(league),
                        "fixture_job_id": fixture_job.id,
                        "fixtures_processed": fixture_job.records_processed,
                        "fixtures_created": fixture_job.records_created,
                        "fixtures_updated": fixture_job.records_updated,
                        "statistic_fixtures_requested": len(fixture_ids),
                        "statistic_rows_created": stat_job.records_created if stat_job else 0,
                        "statistic_rows_updated": stat_job.records_updated if stat_job else 0,
                        "statistic_rows_failed": stat_job.records_failed if stat_job else 0,
                    }
                )
        print(
            json.dumps(
                {
                    "provider": "statsbomb",
                    "cost": "free",
                    "live": False,
                    "leagues": summaries,
                    "unavailable_requested_leagues": ["super-lig"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        await provider.aclose()
        await close_database()


async def _ensure_open_data_database(session: AsyncSession) -> None:
    foreign_job = await session.scalar(
        select(IngestionJob.id).where(IngestionJob.provider != "statsbomb").limit(1)
    )
    foreign_stat = await session.scalar(
        select(PlayerFixtureStats.id).where(PlayerFixtureStats.data_source != "statsbomb").limit(1)
    )
    if foreign_job is not None or foreign_stat is not None:
        raise ValidationError(
            "This database contains another provider's data. Use a separate open-data database."
        )


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except (SotAnalyzerError, ValueError) as exc:
        print(f"Open-data sync failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
