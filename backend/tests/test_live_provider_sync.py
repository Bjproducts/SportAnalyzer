"""Live-provider contracts stay deterministic and network-free under test."""

from __future__ import annotations

import json

import httpx

from app.ingestion.api_football import ApiFootballProvider
from app.ingestion.fake import FakeFootballProvider
from app.ingestion.leagues import TRACKED_LEAGUES, TrackedLeague, resolve_leagues
from app.ingestion.sync import sync_leagues


def test_supported_live_league_ids_and_aliases_are_stable():
    assert {league.slug: league.provider_id for league in TRACKED_LEAGUES} == {
        "mls": 253,
        "epl": 39,
        "la-liga": 140,
        "bundesliga": 78,
        "ligue-1": 61,
        "serie-a": 135,
        "super-lig": 203,
    }
    assert [league.slug for league in resolve_leagues("EPL,german-league,Süper-Lig")] == [
        "epl",
        "bundesliga",
        "super-lig",
    ]


async def test_api_football_player_stats_uses_fixture_context_and_tracks_quota():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = {
            "errors": [],
            "response": [
                {
                    "team": {"id": 10, "name": "Home"},
                    "players": [
                        {
                            "player": {"id": 99, "name": "Live Player"},
                            "statistics": [
                                {
                                    "games": {
                                        "minutes": 90,
                                        "number": 9,
                                        "position": "F",
                                        "rating": "7.2",
                                        "substitute": False,
                                    },
                                    "shots": {"total": 4, "on": 2},
                                    "goals": {"total": 1, "assists": 0},
                                    "passes": {"key": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        return httpx.Response(
            200,
            content=json.dumps(payload),
            headers={
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "87",
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "8",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://provider.test", transport=httpx.MockTransport(handler)
    )
    provider = ApiFootballProvider(
        api_key="test-key",
        base_url="https://provider.test",
        calls_per_minute=10_000,
        timeout_seconds=2,
        max_retries=0,
        client=client,
    )
    try:
        rows = await provider.get_player_fixture_statistics(
            123,
            home_team_id=10,
            away_team_id=20,
        )
        assert calls == ["/fixtures/players"]
        assert rows[0].home is True
        assert rows[0].opponent_id == 20
        assert rows[0].shots_on_target == 2
        assert provider.quota is not None
        assert provider.quota.daily_remaining == 87
        assert provider.quota.minute_remaining == 8
    finally:
        await client.aclose()


async def test_incremental_sync_only_requests_finished_fixtures_missing_statistics(session):
    demo = (TrackedLeague("demo", 9001, "SOT Demo League", "England"),)

    first = await sync_leagues(
        session,
        FakeFootballProvider(),
        demo,
        season=2025,
        max_stat_fixtures_per_league=2,
    )
    second = await sync_leagues(
        session,
        FakeFootballProvider(),
        demo,
        season=2025,
        max_stat_fixtures_per_league=2,
    )
    statistics_only = await sync_leagues(
        session,
        FakeFootballProvider(),
        demo,
        season=2025,
        max_stat_fixtures_per_league=2,
        refresh_fixtures=False,
    )

    assert first.leagues[0].fixtures_created == 12
    assert first.leagues[0].statistic_fixtures_requested == 2
    assert first.leagues[0].statistic_rows_created == 12
    assert second.leagues[0].fixtures_updated == 12
    assert second.leagues[0].statistic_fixtures_requested == 2
    assert second.leagues[0].statistic_rows_created == 12
    assert statistics_only.leagues[0].fixture_job_id is None
    assert statistics_only.leagues[0].fixtures_processed == 0
    assert statistics_only.leagues[0].statistic_fixtures_requested == 2
    assert statistics_only.leagues[0].statistic_rows_created == 12
