"""SportsAPI Pro normalization remains deterministic and network-free."""

from __future__ import annotations

import json

import httpx

from app.core.enums import DataQualityStatus, FixtureStatus
from app.ingestion.sports_api_leagues import (
    SPORTS_API_PRO_LEAGUES,
    SPORTS_API_PRO_SEASON_IDS,
    resolve_sports_api_leagues,
)
from app.ingestion.sports_api_pro import SportsApiProProvider


def test_sports_api_league_ids_are_stable():
    assert {league.slug: league.provider_id for league in SPORTS_API_PRO_LEAGUES} == {
        "mls": 242,
        "epl": 17,
        "la-liga": 8,
        "bundesliga": 35,
        "ligue-1": 34,
        "serie-a": 23,
        "super-lig": 52,
        "leagues-cup": 13783,
    }
    assert [league.slug for league in resolve_sports_api_leagues("EPL,MLS,Süper-Lig")] == [
        "epl",
        "mls",
        "super-lig",
    ]
    assert resolve_sports_api_leagues("north-america-tournament")[0].slug == "leagues-cup"
    assert SPORTS_API_PRO_SEASON_IDS[(242, 2026)] == 86668


async def test_verified_season_id_skips_catalog_request():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/events/last/0"):
            return httpx.Response(200, json={"success": True, "data": {"events": [_event()]}})
        return httpx.Response(404, json={"success": False})

    client = httpx.AsyncClient(
        base_url="https://provider.test/", transport=httpx.MockTransport(handler)
    )
    provider = _provider(client)
    provider.remember_season(17, 2025, 900)
    try:
        fixtures = await provider.get_fixtures(17, 2025)
        assert len(fixtures) == 1
        assert "/api/tournaments/17/seasons" not in calls
    finally:
        await client.aclose()


async def test_fixtures_resolve_season_and_normalize_latest_page():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/tournaments/17/seasons":
            payload = {
                "success": True,
                "seasons": [{"id": 900, "name": "Premier League 25/26", "year": "25/26"}],
            }
        elif request.url.path.endswith("/events/last/0"):
            payload = {"success": True, "data": {"events": [_event()]}}
        elif request.url.path.endswith("/events/next/0"):
            return httpx.Response(404, json={"success": False})
        else:
            return httpx.Response(404, json={"success": False})
        return httpx.Response(
            200,
            content=json.dumps(payload),
            headers={"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "88"},
        )

    client = httpx.AsyncClient(
        base_url="https://provider.test/", transport=httpx.MockTransport(handler)
    )
    provider = _provider(client)
    try:
        fixtures = await provider.get_fixtures(17, 2025)
        assert calls == [
            "/api/tournaments/17/seasons",
            "/api/tournament/17/season/900/events/last/0",
            "/api/tournament/17/season/900/events/next/0",
        ]
        assert len(fixtures) == 1
        fixture = fixtures[0]
        assert fixture.id == 123
        assert fixture.competition.id == 17
        assert fixture.season_year == 2025
        assert fixture.status is FixtureStatus.FINISHED
        assert fixture.home_team.id == 10
        assert fixture.away_team.id == 20
        assert fixture.home_score == 2
        assert fixture.away_score == 1
        assert fixture.round == "Matchweek 5"
        assert provider.quota is not None
        assert provider.quota.daily_remaining == 88
    finally:
        await client.aclose()


async def test_new_season_can_have_upcoming_events_without_completed_events():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tournaments/17/seasons":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "seasons": [{"id": 901, "name": "Premier League 26/27", "year": "26/27"}],
                },
            )
        if request.url.path.endswith("/events/last/0"):
            return httpx.Response(404, json={"success": False})
        if request.url.path.endswith("/events/next/0"):
            event = _event()
            event["status"] = {"code": 0, "type": "notstarted"}
            return httpx.Response(200, json={"success": True, "data": {"events": [event]}})
        return httpx.Response(404, json={"success": False})

    client = httpx.AsyncClient(
        base_url="https://provider.test/", transport=httpx.MockTransport(handler)
    )
    provider = _provider(client)
    try:
        fixtures = await provider.get_fixtures(17, 2026)
        assert len(fixtures) == 1
        assert fixtures[0].season_year == 2026
        assert fixtures[0].status is FixtureStatus.SCHEDULED
    finally:
        await client.aclose()


async def test_player_statistics_preserve_missing_sot_and_skip_unused_substitutes():
    payload = {
        "success": True,
        "data": {
            "home": [
                {
                    "player": {"id": 101, "name": "Home Shooter", "position": "F"},
                    "shirtNumber": 9,
                    "position": "F",
                    "substitute": False,
                    "statistics": {
                        "minutesPlayed": 90,
                        "totalShots": 3,
                        "onTargetScoringAttempt": 2,
                        "goals": 1,
                        "goalAssist": 0,
                        "keyPass": 1,
                        "touches": 40,
                        "rating": 7.5,
                    },
                },
                {
                    "player": {"id": 102, "name": "Unused Sub", "position": "M"},
                    "substitute": True,
                    "statistics": {"totalShots": 0},
                },
            ],
            "away": [
                {
                    "player": {"id": 201, "name": "Away Shooter", "position": "M"},
                    "substitute": False,
                    "statistics": {"minutesPlayed": 90, "totalShots": 1},
                },
                {
                    "player": {"id": 202, "name": "Unknown Coverage", "position": "D"},
                    "substitute": False,
                    "statistics": {"minutesPlayed": 90},
                },
            ],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/match/123/player-statistics"
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(
        base_url="https://provider.test/", transport=httpx.MockTransport(handler)
    )
    provider = _provider(client)
    try:
        rows = await provider.get_player_fixture_statistics(123, home_team_id=10, away_team_id=20)
        assert [row.player.id for row in rows] == [101, 201, 202]

        home = rows[0]
        assert home.home is True
        assert home.started is True
        assert home.shots_on_target == 2
        assert home.goals == 1
        assert home.team_shots == 3
        assert home.team_shots_on_target == 2

        away = rows[1]
        assert away.shots == 1
        assert away.shots_on_target == 0
        assert away.data_quality_status is DataQualityStatus.COMPLETE
        assert away.team_shots == 1
        assert away.team_shots_on_target == 0

        unknown = rows[2]
        assert unknown.shots is None
        assert unknown.shots_on_target is None
        assert unknown.data_quality_status is DataQualityStatus.MISSING_SOT
    finally:
        await client.aclose()


def _provider(client: httpx.AsyncClient) -> SportsApiProProvider:
    return SportsApiProProvider(
        api_key="test-key",
        base_url="https://provider.test",
        calls_per_minute=10_000,
        timeout_seconds=2,
        max_retries=0,
        history_pages=1,
        client=client,
    )


def _event() -> dict[str, object]:
    return {
        "id": 123,
        "tournament": {
            "name": "Premier League",
            "uniqueTournament": {
                "id": 17,
                "name": "Premier League",
                "category": {"name": "England"},
            },
        },
        "season": {"id": 900, "name": "Premier League 25/26", "year": "25/26"},
        "roundInfo": {"round": 5},
        "status": {"code": 100, "type": "finished"},
        "homeTeam": {
            "id": 10,
            "name": "Home FC",
            "shortName": "Home",
            "country": {"name": "England"},
        },
        "awayTeam": {
            "id": 20,
            "name": "Away FC",
            "shortName": "Away",
            "country": {"name": "England"},
        },
        "homeScore": {"current": 2},
        "awayScore": {"current": 1},
        "venue": {"name": "Test Ground"},
        "startTimestamp": 1_750_000_000,
    }
