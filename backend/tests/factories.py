"""Object factories for database tests.

Each helper returns a valid, minimally-populated model instance so that tests
only have to state the field they actually care about.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

from app.core.enums import CompetitionType, DataQualityStatus, FixtureStatus
from app.models import (
    Competition,
    Fixture,
    Player,
    PlayerFixtureStats,
    Season,
    Team,
)

_ids = count(1)


def next_provider_id() -> int:
    """Unique provider id, so factories never collide on unique constraints."""
    return next(_ids)


def make_competition(**overrides: Any) -> Competition:
    competition_type = overrides.pop("competition_type", CompetitionType.LEAGUE)
    defaults: dict[str, Any] = {
        "provider_competition_id": next_provider_id(),
        "name": "Premier League",
        "country": "England",
        "competition_type": competition_type,
        "is_competitive": Competition.derive_is_competitive(competition_type),
    }
    return Competition(**{**defaults, **overrides})


def make_season(competition: Competition, **overrides: Any) -> Season:
    defaults: dict[str, Any] = {
        "competition": competition,
        "season_year": 2024,
        "label": "2024/25",
        "is_current": True,
    }
    return Season(**{**defaults, **overrides})


def make_team(name: str = "Arsenal", **overrides: Any) -> Team:
    team = Team(
        **{
            "provider_team_id": next_provider_id(),
            "name": name,
            "short_name": name[:3].upper(),
            "country": "England",
            **overrides,
        }
    )
    team.apply_search_name()
    return team


def make_player(full_name: str = "Bukayo Saka", **overrides: Any) -> Player:
    player = Player(
        **{
            "provider_player_id": next_provider_id(),
            "full_name": full_name,
            "common_name": overrides.pop("common_name", full_name),
            **overrides,
        }
    )
    player.apply_search_names()
    return player


def make_fixture(
    competition: Competition,
    season: Season,
    home_team: Team,
    away_team: Team,
    *,
    days_ago: int = 7,
    **overrides: Any,
) -> Fixture:
    defaults: dict[str, Any] = {
        "provider_fixture_id": next_provider_id(),
        "competition": competition,
        "season": season,
        "home_team": home_team,
        "away_team": away_team,
        "fixture_date": datetime.now(UTC) - timedelta(days=days_ago),
        "status": FixtureStatus.FINISHED,
        "home_score": 2,
        "away_score": 1,
    }
    return Fixture(**{**defaults, **overrides})


def make_stats(
    fixture: Fixture,
    player: Player,
    team: Team,
    opponent: Team,
    **overrides: Any,
) -> PlayerFixtureStats:
    """Build a player-fixture row with derived fields already applied."""
    defaults: dict[str, Any] = {
        "fixture": fixture,
        "player": player,
        "team": team,
        "opponent": opponent,
        "home": True,
        "started": True,
        "substitute_appearance": False,
        "minutes_played": 90,
        "position": "RW",
        "shots": 3,
        "shots_on_target": 1,
        "goals": 0,
        "assists": 0,
        "data_source": "test",
        "data_quality_status": DataQualityStatus.COMPLETE,
    }
    stats = PlayerFixtureStats(**{**defaults, **overrides})
    stats.apply_derived_fields()
    return stats
