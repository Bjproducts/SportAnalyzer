"""Builders for analytics test inputs.

``line()`` produces a valid start with 1 SOT by default, so each test only has
to state the field it actually cares about.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.analytics.models import MatchStatLine
from app.core.enums import DataQualityStatus

BASE_DATE = datetime(2025, 1, 1, tzinfo=UTC)


def line(
    *,
    day: int = 1,
    sot: int | None = 1,
    shots: int | None = 3,
    started: bool = True,
    home: bool = True,
    minutes: int | None = 90,
    quality: DataQualityStatus = DataQualityStatus.COMPLETE,
    fixture_id: int | None = None,
    **overrides: Any,
) -> MatchStatLine:
    """One match record. ``day`` orders matches - higher is more recent."""
    defaults: dict[str, Any] = {
        "fixture_id": fixture_id if fixture_id is not None else day,
        "player_id": 1,
        "team_id": 10,
        "opponent_id": 20,
        "fixture_date": BASE_DATE + timedelta(days=day),
        "competition_id": 100,
        "season_id": 1000,
        "home": home,
        "started": started,
        "substitute_appearance": not started,
        "minutes_played": minutes,
        "shots": shots,
        "shots_on_target": sot,
        "data_quality_status": quality,
    }
    return MatchStatLine(**{**defaults, **overrides})


def series(sots: list[int | None], **common: Any) -> list[MatchStatLine]:
    """A run of starts, oldest first, with the given SOT values.

    ``series([1, 0, 2])`` -> day 1 has 1 SOT, day 2 has 0, day 3 has 2.
    """
    return [line(day=index + 1, sot=value, **common) for index, value in enumerate(sots)]
