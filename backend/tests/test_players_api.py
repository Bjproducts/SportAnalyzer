"""Phase 4 player API tests over a realistic relational match history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as database_module
from app.core.enums import CompetitionType, DataQualityStatus, FixtureStatus
from app.database import Database
from app.main import create_app
from app.repositories.players import PlayerMatchRepository
from tests.factories import (
    make_competition,
    make_fixture,
    make_player,
    make_season,
    make_stats,
    make_team,
)


@dataclass(frozen=True, slots=True)
class ApiWorld:
    player_id: int
    empty_player_id: int
    team_id: int
    league_id: int
    cup_id: int
    opponent_a_id: int
    opponent_b_id: int


@pytest.fixture
async def api_world(session: AsyncSession) -> ApiWorld:
    league = make_competition(name="Premier League")
    league_season = make_season(league, season_year=2024, label="2024/25")
    cup = make_competition(name="FA Cup", competition_type=CompetitionType.DOMESTIC_CUP)
    cup_season = make_season(cup, season_year=2023, label="2023/24")
    friendly = make_competition(
        name="Club Friendly",
        competition_type=CompetitionType.FRIENDLY,
    )
    friendly_season = make_season(friendly, season_year=2024, label="2024")

    arsenal = make_team("Arsenal")
    chelsea = make_team("Chelsea")
    liverpool = make_team("Liverpool")
    player = make_player(
        "Martin Ødegaard",
        common_name="Martin Ødegaard",
        current_team=arsenal,
        nationality="Norway",
        primary_position="Attacking Midfielder",
    )
    empty_player = make_player(
        "Bukayo Saka",
        common_name="Bukayo Saka",
        current_team=arsenal,
    )

    def match(
        *,
        day: int,
        competition,
        season,
        opponent,
        home: bool,
        fixture_status: FixtureStatus = FixtureStatus.FINISHED,
        **stats_overrides,
    ):
        fixture = make_fixture(
            competition,
            season,
            arsenal if home else opponent,
            opponent if home else arsenal,
            fixture_date=datetime(2025, 1, day, 15, tzinfo=UTC),
            status=fixture_status,
        )
        return make_stats(
            fixture,
            player,
            arsenal,
            opponent,
            home=home,
            **stats_overrides,
        )

    stats = [
        match(
            day=1,
            competition=league,
            season=league_season,
            opponent=chelsea,
            home=True,
            shots=2,
            shots_on_target=1,
            minutes_played=90,
            team_shots=12,
            team_shots_on_target=5,
        ),
        match(
            day=2,
            competition=league,
            season=league_season,
            opponent=chelsea,
            home=False,
            shots=1,
            shots_on_target=0,
            minutes_played=90,
            team_shots=10,
            team_shots_on_target=4,
        ),
        match(
            day=3,
            competition=league,
            season=league_season,
            opponent=chelsea,
            home=True,
            shots=None,
            shots_on_target=None,
            minutes_played=30,
            position="AM",
            team_shots=9,
            team_shots_on_target=3,
            data_quality_status=DataQualityStatus.MISSING_SOT,
        ),
        match(
            day=4,
            competition=league,
            season=league_season,
            opponent=chelsea,
            home=False,
            started=False,
            substitute_appearance=True,
            shots=3,
            shots_on_target=2,
            minutes_played=25,
            team_shots=11,
            team_shots_on_target=5,
        ),
        match(
            day=5,
            competition=league,
            season=league_season,
            opponent=chelsea,
            home=True,
            shots=4,
            shots_on_target=2,
            minutes_played=80,
            team_shots=14,
            team_shots_on_target=6,
        ),
        match(
            day=6,
            competition=friendly,
            season=friendly_season,
            opponent=liverpool,
            home=True,
            shots=5,
            shots_on_target=3,
        ),
        match(
            day=7,
            competition=league,
            season=league_season,
            opponent=liverpool,
            home=True,
            fixture_status=FixtureStatus.SCHEDULED,
            shots=5,
            shots_on_target=3,
        ),
        match(
            day=8,
            competition=cup,
            season=cup_season,
            opponent=liverpool,
            home=False,
            shots=3,
            shots_on_target=1,
            minutes_played=90,
            team_shots=13,
            team_shots_on_target=5,
        ),
    ]
    # Simulate an older imported row that predates the stored derived field;
    # the response mapper must still derive a truthful early-exit value.
    stats[0].early_exit = None
    session.add_all([*stats, empty_player])
    await session.commit()

    return ApiWorld(
        player_id=player.id,
        empty_player_id=empty_player.id,
        team_id=arsenal.id,
        league_id=league.id,
        cup_id=cup.id,
        opponent_a_id=chelsea.id,
        opponent_b_id=liverpool.id,
    )


@pytest.fixture
async def api_client(database: Database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database_module, "_database", database)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_player_search_is_accent_folded_and_returns_team_context(api_client, api_world):
    response = await api_client.get("/api/players", params={"q": "Odegaard"})

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["id"] == api_world.player_id
    assert body["items"][0]["display_name"] == "Martin Ødegaard"
    assert body["items"][0]["current_team"]["name"] == "Arsenal"


async def test_player_listing_is_paginated(api_client, api_world):
    first = await api_client.get("/api/players", params={"page_size": 1})
    second = await api_client.get("/api/players", params={"page_size": 1, "page": 2})

    assert first.json()["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]


async def test_search_with_no_searchable_characters_returns_an_empty_page(api_client):
    response = await api_client.get("/api/players", params={"q": "%%"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 0


async def test_player_profile_and_structured_not_found_response(api_client, api_world):
    response = await api_client.get(f"/api/players/{api_world.player_id}")
    missing = await api_client.get("/api/players/999999")

    assert response.status_code == 200
    assert response.json()["nationality"] == "Norway"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert missing.json()["error"]["details"]["entity"] == "Player"


async def test_default_match_history_is_starts_only_competitive_finished_and_newest_first(
    api_client, api_world
):
    response = await api_client.get(f"/api/players/{api_world.player_id}/matches")

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 5
    assert [item["fixture_date"][:10] for item in body["items"]] == [
        "2025-01-08",
        "2025-01-05",
        "2025-01-03",
        "2025-01-02",
        "2025-01-01",
    ]
    assert all(item["started"] for item in body["items"])


async def test_all_appearances_includes_substitutes_but_not_friendlies(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={"starts_only": "false"},
    )

    body = response.json()
    assert body["pagination"]["total"] == 6
    substitute = next(item for item in body["items"] if item["substitute_appearance"])
    assert substitute["fixture_date"].startswith("2025-01-04")


async def test_missing_sot_is_neutral_and_early_exit_is_visible(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={"position": "AM"},
    )

    match = response.json()["items"][0]
    assert match["shots_on_target"] is None
    assert match["one_plus_sot"] is None
    assert match["two_plus_sot"] is None
    assert match["early_exit"] is True
    assert match["data_quality_status"] == "missing_sot"


async def test_missing_stored_early_exit_is_recomputed_from_minutes(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={"date_from": "2025-01-01", "date_to": "2025-01-01"},
    )

    assert response.json()["items"][0]["early_exit"] is False


@pytest.mark.parametrize(
    ("params", "expected_dates"),
    [
        ({"venue": "away"}, ["2025-01-08", "2025-01-02"]),
        ({"minimum_minutes": 85}, ["2025-01-08", "2025-01-02", "2025-01-01"]),
        ({"last_n": 2}, ["2025-01-08", "2025-01-05"]),
        ({"date_from": "2025-01-03", "date_to": "2025-01-05"}, ["2025-01-05", "2025-01-03"]),
        (
            {"sot_threshold": 0},
            ["2025-01-08", "2025-01-05", "2025-01-02", "2025-01-01"],
        ),
        ({"sot_threshold": 2}, ["2025-01-05"]),
    ],
)
async def test_match_filters(params, expected_dates, api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params=params,
    )

    assert response.status_code == 200
    assert [item["fixture_date"][:10] for item in response.json()["items"]] == expected_dates


async def test_database_identifier_filters_work_together(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={
            "competition_id": api_world.cup_id,
            "season": 2023,
            "opponent_id": api_world.opponent_b_id,
            "team_id": api_world.team_id,
            "venue": "away",
        },
    )

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 1
    assert response.json()["items"][0]["competition"]["name"] == "FA Cup"


async def test_match_pagination_respects_last_n_cap(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={"last_n": 3, "page": 2, "page_size": 2},
    )

    assert response.json()["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }
    assert [item["fixture_date"][:10] for item in response.json()["items"]] == ["2025-01-03"]


async def test_page_beyond_last_n_cap_is_empty_but_keeps_the_total(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/matches",
        params={"last_n": 1, "page": 2, "page_size": 1},
    )

    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 1


async def test_summary_excludes_missing_sot_from_rates(api_client, api_world):
    response = await api_client.get(f"/api/players/{api_world.player_id}/sot-summary")

    assert response.status_code == 200
    body = response.json()
    one_plus = body["summary"]["threshold_rates"]["1"]
    assert (one_plus["successes"], one_plus["valid"], one_plus["missing"]) == (3, 4, 1)
    assert one_plus["percentage"] == 0.75
    assert body["summary"]["threshold_rates"]["2"]["successes"] == 1
    assert body["summary"]["team_sot_share"] == 0.2
    assert body["recent_form"]["5"]["starts_available"] == 5


async def test_summary_can_include_substitute_appearance_counts_without_changing_start_rates(
    api_client, api_world
):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/sot-summary",
        params={"starts_only": "false"},
    )

    summary = response.json()["summary"]
    assert summary["total_appearances"] == 6
    assert summary["total_starts"] == 5
    assert summary["substitute_appearances"] == 1
    assert summary["threshold_rates"]["1"]["valid"] == 4


async def test_empty_player_has_an_honest_empty_summary(api_client, api_world):
    response = await api_client.get(f"/api/players/{api_world.empty_player_id}/sot-summary")

    summary = response.json()["summary"]
    assert summary["total_starts"] == 0
    assert summary["threshold_rates"]["1"]["percentage"] is None
    assert response.json()["recent_form"]["5"]["starts_available"] == 0


async def test_splits_report_venue_and_group_sample_sizes(api_client, api_world):
    response = await api_client.get(f"/api/players/{api_world.player_id}/splits")

    assert response.status_code == 200
    body = response.json()
    assert (body["venue"]["home"]["successes"], body["venue"]["home"]["valid"]) == (2, 2)
    assert body["venue"]["home"]["missing"] == 1
    assert body["venue"]["away"]["percentage"] == 0.5
    assert {entry["label"] for entry in body["competitions"]} == {"Premier League", "FA Cup"}


async def test_split_minimum_starts_and_threshold_are_applied(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/splits",
        params={"minimum_starts": 2, "threshold": 2},
    )

    body = response.json()
    assert body["threshold"] == 2
    assert [entry["label"] for entry in body["competitions"]] == ["Premier League"]
    assert [entry["label"] for entry in body["opponents"]] == ["Chelsea"]
    assert body["venue"]["home"]["successes"] == 1


async def test_streaks_report_latest_failure_and_missing_gap(api_client, api_world):
    response = await api_client.get(f"/api/players/{api_world.player_id}/streaks")

    assert response.status_code == 200
    streak = response.json()["streak"]
    assert streak["current"] == 2
    assert streak["longest"] == 2
    assert streak["missing_in_window"] == 1
    assert streak["reliable"] is False
    assert streak["last_failure_date"].startswith("2025-01-02")
    assert streak["starts_since_last_failure"] == 3


async def test_streak_filters_are_applied_before_calculation(api_client, api_world):
    response = await api_client.get(
        f"/api/players/{api_world.player_id}/streaks",
        params={"venue": "home"},
    )

    streak = response.json()["streak"]
    assert streak["current"] == 2
    assert streak["never_failed"] is True
    assert streak["missing_in_window"] == 1


@pytest.mark.parametrize(
    "path",
    ["matches", "sot-summary", "splits", "streaks"],
)
async def test_analytics_endpoints_return_404_for_unknown_players(path, api_client):
    response = await api_client.get(f"/api/players/999999/{path}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/players", {"q": "x"}),
        ("/api/players", {"q": "  "}),
        ("/api/players", {"page_size": 101}),
        ("/api/players/1/matches", {"venue": "neutral"}),
        ("/api/players/1/matches", {"minimum_minutes": -1}),
        ("/api/players/1/matches", {"position": "  "}),
        (
            "/api/players/1/matches",
            {"date_from": "2025-02-01", "date_to": "2025-01-01"},
        ),
        ("/api/players/1/splits", {"threshold": 0}),
        ("/api/players/1/streaks", {"unexpected": "value"}),
    ],
)
async def test_query_validation_returns_the_structured_error_envelope(path, params, api_client):
    response = await api_client.get(path, params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"]["problems"]


def test_repository_mapper_normalises_aware_fixture_dates_to_utc():
    stats = SimpleNamespace(
        fixture_id=1,
        player_id=1,
        team_id=1,
        opponent_id=2,
        home=True,
        started=True,
        substitute_appearance=False,
        minutes_played=90,
        position="RW",
        shots=1,
        shots_on_target=1,
        goals=0,
        assists=0,
        team_shots=10,
        team_shots_on_target=4,
        early_exit=False,
        data_quality_status=DataQualityStatus.COMPLETE,
    )
    line = PlayerMatchRepository._to_match_line(
        stats,  # type: ignore[arg-type]
        datetime.fromisoformat("2025-01-01T10:00:00+02:00"),
        1,
        1,
        "Premier League",
        "2024/25",
        "Arsenal",
        "Chelsea",
    )

    assert line.fixture_date.isoformat() == "2025-01-01T08:00:00+00:00"
