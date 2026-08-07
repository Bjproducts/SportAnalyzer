"""Quota-aware SportsAPI Pro league synchronization command."""

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
from app.ingestion.sports_api_leagues import (
    SPORTS_API_PRO_SEASON_IDS,
    resolve_sports_api_leagues,
)
from app.ingestion.sports_api_pro import SportsApiProProvider
from app.ingestion.sync import sync_leagues
from app.models import IngestionJob, PlayerFixtureStats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync fixtures and player SOT statistics from SportsAPI Pro."
    )
    parser.add_argument("--season", type=int, required=True, help="Season starting year.")
    parser.add_argument("--leagues", default="all", help="Comma-separated slugs or 'all'.")
    parser.add_argument(
        "--max-stat-fixtures-per-league",
        type=int,
        default=2,
        help="Newest missing finished fixtures per league (default: 2; 0: fixtures only).",
    )
    parser.add_argument(
        "--all-missing-statistics",
        action="store_true",
        help="Import all missing fixture statistics available locally.",
    )
    parser.add_argument(
        "--statistics-only",
        action="store_true",
        help="Skip fixture API calls and resume statistics for fixtures already in the database.",
    )
    parser.add_argument(
        "--history-pages",
        type=int,
        choices=range(1, 101),
        metavar="1-100",
        help="Override completed-match pages for this run (30 fixtures/page).",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.football_provider.strip().casefold() != "sportsapipro":
        raise ValueError("Set FOOTBALL_PROVIDER=sportsapipro before this sync.")
    leagues = resolve_sports_api_leagues(args.leagues)
    if args.statistics_only and args.history_pages is not None:
        raise ValueError("--history-pages cannot be used with --statistics-only.")
    if args.history_pages is not None:
        settings = settings.model_copy(update={"sports_api_pro_history_pages": args.history_pages})
    limit = None if args.all_missing_statistics else args.max_stat_fixtures_per_league
    database = init_database(settings)
    try:
        async with database.session() as session:
            await _ensure_sports_api_database(session)
            provider = create_provider(settings)
            if isinstance(provider, SportsApiProProvider):
                for league in leagues:
                    season_id = SPORTS_API_PRO_SEASON_IDS.get((league.provider_id, args.season))
                    if season_id is not None:
                        provider.remember_season(league.provider_id, args.season, season_id)
            report = await sync_leagues(
                session,
                provider,
                leagues,
                season=args.season,
                max_stat_fixtures_per_league=limit,
                refresh_fixtures=not args.statistics_only,
            )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    finally:
        await close_database()


async def _ensure_sports_api_database(session: AsyncSession) -> None:
    foreign_job = await session.scalar(
        select(IngestionJob.id).where(IngestionJob.provider != "sportsapipro").limit(1)
    )
    foreign_stat = await session.scalar(
        select(PlayerFixtureStats.id)
        .where(PlayerFixtureStats.data_source != "sportsapipro")
        .limit(1)
    )
    if foreign_job is not None or foreign_stat is not None:
        raise ValidationError(
            "This database contains another provider's data. Use a separate SportsAPI database."
        )


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except (SotAnalyzerError, ValueError) as exc:
        print(f"SportsAPI sync failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
