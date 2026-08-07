"""Command-line entry point for quota-aware live league synchronization."""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import SotAnalyzerError, ValidationError
from app.database import close_database, init_database
from app.ingestion.factory import create_provider
from app.ingestion.leagues import resolve_leagues
from app.ingestion.sync import sync_leagues
from app.models import IngestionJob, PlayerFixtureStats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync fixtures and missing SOT player statistics from API-Football."
    )
    parser.add_argument("--season", type=int, required=True, help="Season starting year.")
    parser.add_argument(
        "--leagues",
        default="all",
        help="Comma-separated slugs, or 'all' (default).",
    )
    parser.add_argument(
        "--max-stat-fixtures-per-league",
        type=int,
        default=10,
        help="Newest missing finished fixtures per league (default: 10; 0: fixtures only).",
    )
    parser.add_argument(
        "--all-missing-statistics",
        action="store_true",
        help="Import every missing finished fixture; use only with sufficient daily quota.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.football_provider.strip().casefold() != "apifootball":
        raise ValueError(
            "Set FOOTBALL_PROVIDER=apifootball and FOOTBALL_API_KEY in .env before live sync."
        )
    leagues = resolve_leagues(args.leagues)
    limit = None if args.all_missing_statistics else args.max_stat_fixtures_per_league
    database = init_database(settings)
    try:
        async with database.session() as session:
            await _ensure_live_provider_database(session)
            report = await sync_leagues(
                session,
                create_provider(settings),
                leagues,
                season=args.season,
                max_stat_fixtures_per_league=limit,
            )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    finally:
        await close_database()


async def _ensure_live_provider_database(session: AsyncSession) -> None:
    fake_job = await session.scalar(
        select(IngestionJob.id).where(IngestionJob.provider != "apifootball").limit(1)
    )
    foreign_stat = await session.scalar(
        select(PlayerFixtureStats.id)
        .where(PlayerFixtureStats.data_source != "apifootball")
        .limit(1)
    )
    if fake_job is not None or foreign_stat is not None:
        raise ValidationError(
            "This database already contains another provider's data. Use a fresh live database; "
            "provider identifiers cannot be mixed safely."
        )


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except (SotAnalyzerError, ValueError) as exc:
        print(f"Live sync failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
