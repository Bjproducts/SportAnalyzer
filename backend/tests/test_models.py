"""Database schema and model behaviour tests.

These run against SQLite with `PRAGMA foreign_keys=ON`, so constraint
violations fail here the same way they would on PostgreSQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.analytics.rules import is_early_exit
from app.core.enums import CompetitionType, DataQualityStatus
from app.core.text import normalize_name
from app.models import Player, PlayerFixtureStats
from tests.factories import (
    make_competition,
    make_fixture,
    make_player,
    make_season,
    make_stats,
    make_team,
)


@pytest.fixture
async def world(session):
    """A minimal populated database: one fixture between two teams."""
    competition = make_competition()
    season = make_season(competition)
    arsenal = make_team("Arsenal")
    chelsea = make_team("Chelsea")
    player = make_player("Bukayo Saka")
    player.current_team = arsenal
    fixture = make_fixture(competition, season, arsenal, chelsea)

    session.add_all([competition, season, arsenal, chelsea, player, fixture])
    await session.flush()
    return {
        "session": session,
        "competition": competition,
        "season": season,
        "home": arsenal,
        "away": chelsea,
        "player": player,
        "fixture": fixture,
    }


# --- Unique constraint -----------------------------------------------------


async def test_duplicate_fixture_player_team_is_rejected(world):
    """The (fixture, player, team) unique constraint blocks duplicate imports."""
    session = world["session"]
    session.add(make_stats(world["fixture"], world["player"], world["home"], world["away"]))
    await session.flush()

    session.add(make_stats(world["fixture"], world["player"], world["home"], world["away"]))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_same_player_may_appear_in_different_fixtures(world):
    session = world["session"]
    second = make_fixture(
        world["competition"], world["season"], world["home"], world["away"], days_ago=14
    )
    session.add(second)
    await session.flush()

    session.add_all(
        [
            make_stats(world["fixture"], world["player"], world["home"], world["away"]),
            make_stats(second, world["player"], world["home"], world["away"]),
        ]
    )
    await session.flush()

    rows = (await session.execute(select(PlayerFixtureStats))).scalars().all()
    assert len(rows) == 2


# --- Check constraints -----------------------------------------------------


async def test_cannot_be_both_starter_and_substitute(world):
    session = world["session"]
    session.add(
        make_stats(
            world["fixture"],
            world["player"],
            world["home"],
            world["away"],
            started=True,
            substitute_appearance=True,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_team_and_opponent_must_differ(world):
    session = world["session"]
    session.add(
        make_stats(world["fixture"], world["player"], world["home"], world["home"]),
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_shots_on_target_cannot_exceed_shots(world):
    session = world["session"]
    session.add(
        make_stats(
            world["fixture"],
            world["player"],
            world["home"],
            world["away"],
            shots=2,
            shots_on_target=3,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_null_shots_on_target_is_allowed(world):
    """Missing SOT must be storable - it is the whole point of the design."""
    session = world["session"]
    session.add(
        make_stats(
            world["fixture"],
            world["player"],
            world["home"],
            world["away"],
            shots=4,
            shots_on_target=None,
            data_quality_status=DataQualityStatus.MISSING_SOT,
        )
    )
    await session.flush()

    row = (await session.execute(select(PlayerFixtureStats))).scalar_one()
    assert row.shots_on_target is None
    assert row.data_quality_status is DataQualityStatus.MISSING_SOT


async def test_negative_shots_are_rejected(world):
    session = world["session"]
    session.add(
        make_stats(world["fixture"], world["player"], world["home"], world["away"], shots=-1)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_rating_outside_zero_to_ten_is_rejected(world):
    session = world["session"]
    session.add(
        make_stats(world["fixture"], world["player"], world["home"], world["away"], rating=11.5)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_minutes_played_above_200_is_rejected(world):
    session = world["session"]
    session.add(
        make_stats(
            world["fixture"], world["player"], world["home"], world["away"], minutes_played=500
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_fixture_teams_must_differ(world):
    session = world["session"]
    session.add(
        make_fixture(
            world["competition"], world["season"], world["home"], world["home"], days_ago=3
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_orm_rejects_an_invalid_enum_value(world):
    """`validate_strings=True` catches a bad value before it reaches the DB."""
    session = world["session"]
    stats = make_stats(world["fixture"], world["player"], world["home"], world["away"])
    stats.data_quality_status = "not_a_real_status"  # type: ignore[assignment]
    session.add(stats)

    with pytest.raises(StatementError, match="not among the defined enum values"):
        await session.flush()


async def test_database_check_constraint_rejects_an_invalid_enum_value(world):
    """The VARCHAR-backed enum carries a real CHECK constraint.

    Goes around the ORM entirely with raw SQL, because the ORM guard above
    would otherwise mask a missing database constraint.
    """
    session = world["session"]
    stats = make_stats(world["fixture"], world["player"], world["home"], world["away"])
    session.add(stats)
    await session.flush()

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "UPDATE player_fixture_stats SET data_quality_status = 'not_a_real_status' "
                "WHERE id = :row_id"
            ),
            {"row_id": stats.id},
        )


# --- Derived fields --------------------------------------------------------


@pytest.mark.parametrize(
    ("started", "minutes", "expected"),
    [
        (True, 30, True),
        (True, 44, True),
        (True, 45, False),
        (True, 90, False),
        (False, 10, False),
        (True, None, None),
    ],
)
async def test_early_exit_is_derived_consistently(world, started, minutes, expected):
    session = world["session"]
    stats = make_stats(
        world["fixture"],
        world["player"],
        world["home"],
        world["away"],
        started=started,
        substitute_appearance=not started,
        minutes_played=minutes,
    )
    session.add(stats)
    await session.flush()

    assert stats.early_exit is expected
    # The stored column must agree with a fresh computation from the rule.
    assert stats.early_exit is is_early_exit(started=started, minutes_played=minutes)


# --- Fixture helpers -------------------------------------------------------


async def test_opponent_and_venue_resolution(world):
    fixture = world["fixture"]
    assert fixture.opponent_id_for(world["home"].id) == world["away"].id
    assert fixture.opponent_id_for(world["away"].id) == world["home"].id
    assert fixture.is_home_for(world["home"].id) is True
    assert fixture.is_home_for(world["away"].id) is False


async def test_opponent_lookup_rejects_a_team_that_did_not_play(world):
    """Returning a plausible-looking id here would corrupt opponent splits."""
    other = make_team("Everton")
    world["session"].add(other)
    await world["session"].flush()

    with pytest.raises(ValueError, match="did not play"):
        world["fixture"].opponent_id_for(other.id)


# --- Name normalisation ----------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Martin Ødegaard", "martin odegaard"),
        ("Kylian Mbappé", "kylian mbappe"),
        ("N'Golo Kanté", "n golo kante"),
        ("Beşiktaş", "besiktas"),
        ("Łukasz Fabiański", "lukasz fabianski"),
        ("Bukayo Saka", "bukayo saka"),
        ("  Extra   Spaces  ", "extra spaces"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_name(given, expected):
    assert normalize_name(given) == expected


async def test_player_search_names_are_populated(session):
    player = make_player("Martin Ødegaard")
    session.add(player)
    await session.flush()

    found = (
        await session.execute(select(Player).where(Player.search_name.like("martin ode%")))
    ).scalar_one()
    assert found.display_name == "Martin Ødegaard"


async def test_player_display_name_prefers_common_name(session):
    player = make_player("Harry Edward Kane", common_name="Harry Kane")
    session.add(player)
    await session.flush()
    assert player.display_name == "Harry Kane"


# --- Competition rules -----------------------------------------------------


@pytest.mark.parametrize(
    ("competition_type", "expected"),
    [
        (CompetitionType.LEAGUE, True),
        (CompetitionType.DOMESTIC_CUP, True),
        (CompetitionType.INTERNATIONAL_CLUB, True),
        (CompetitionType.FRIENDLY, False),
    ],
)
def test_competitive_classification(competition_type, expected):
    from app.models import Competition

    assert Competition.derive_is_competitive(competition_type) is expected


# --- Referential integrity -------------------------------------------------


async def test_foreign_keys_are_enforced(session):
    """Guards the test harness itself: SQLite ignores FKs unless enabled."""
    competition = make_competition()
    season = make_season(competition)
    home = make_team("Arsenal")
    away = make_team("Chelsea")
    session.add_all([competition, season, home, away])
    await session.flush()

    fixture = make_fixture(competition, season, home, away)
    session.add(fixture)
    await session.flush()

    orphan = PlayerFixtureStats(
        fixture_id=fixture.id,
        player_id=999_999,  # no such player
        team_id=home.id,
        opponent_id=away.id,
        home=True,
        started=True,
        substitute_appearance=False,
        data_source="test",
        data_quality_status=DataQualityStatus.COMPLETE,
    )
    session.add(orphan)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_timestamps_are_populated(world):
    session = world["session"]
    stats = make_stats(world["fixture"], world["player"], world["home"], world["away"])
    session.add(stats)
    await session.flush()
    assert stats.created_at is not None
    assert stats.updated_at is not None
