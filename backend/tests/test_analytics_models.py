"""Typed analytics value-object invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from app.analytics.models import RateResult
from app.analytics.summary import build_sot_summary
from tests.analytics_builders import line


def test_match_stat_lines_are_immutable_and_slotted():
    match = line()

    with pytest.raises(FrozenInstanceError):
        match.shots_on_target = 2  # type: ignore[misc]
    assert not hasattr(match, "__dict__")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"fixture_id": 0}, "fixture_id"),
        ({"team_id": 20, "opponent_id": 20}, "must differ"),
        ({"started": True, "substitute_appearance": True}, "both a start"),
        ({"minutes": -1}, "minutes_played"),
        ({"minutes": 201}, "cannot exceed"),
        ({"shots": -1, "sot": 0}, "shots cannot"),
        ({"shots": 1, "sot": 2}, "cannot exceed shots"),
        ({"team_shots": 2, "team_shots_on_target": 3}, "cannot exceed team_shots"),
    ],
)
def test_match_stat_line_rejects_impossible_inputs(overrides: dict[str, object], message: str):
    with pytest.raises(ValueError, match=message):
        line(**overrides)  # type: ignore[arg-type]


def test_match_stat_line_requires_a_timezone_aware_fixture_date():
    with pytest.raises(ValueError, match="timezone-aware"):
        line(fixture_date=datetime(2025, 1, 1))


@pytest.mark.parametrize(
    "rate",
    [
        RateResult(successes=0, valid=0),
        RateResult(successes=0, valid=5, missing=2),
        RateResult(successes=5, valid=5),
    ],
)
def test_valid_rate_results_preserve_count_invariants(rate: RateResult):
    assert 0 <= rate.successes <= rate.valid
    assert rate.total_considered == rate.valid + rate.missing


@pytest.mark.parametrize(
    "kwargs",
    [
        {"successes": -1, "valid": 1},
        {"successes": 0, "valid": -1},
        {"successes": 0, "valid": 1, "missing": -1},
        {"successes": 2, "valid": 1},
    ],
)
def test_rate_results_reject_impossible_counts(kwargs: dict[str, int]):
    with pytest.raises(ValueError):
        RateResult(**kwargs)


def test_summary_rejects_records_from_multiple_players():
    with pytest.raises(ValueError, match="one player"):
        build_sot_summary([line(day=1, player_id=1), line(day=2, player_id=2)])


def test_explicit_summary_player_must_match_the_records():
    with pytest.raises(ValueError, match="does not match"):
        build_sot_summary([line(player_id=1)], player_id=2)
