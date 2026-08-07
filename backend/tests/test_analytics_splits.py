"""Venue, competition, season and opponent split tests."""

from __future__ import annotations

import pytest

from app.analytics.splits import (
    compute_competition_split,
    compute_grouped_split,
    compute_opponent_split,
    compute_position_share,
    compute_season_split,
    compute_venue_splits,
    venue_rate,
)
from app.core.enums import Venue
from tests.analytics_builders import line


def test_venue_splits_handle_mixed_home_away_missing_and_substitute_records():
    lines = [
        line(day=1, home=True, sot=1),
        line(day=2, home=True, sot=0),
        line(day=3, home=False, sot=2),
        line(day=4, home=False, sot=None),
        line(day=5, home=False, sot=0, started=False),
    ]

    splits = compute_venue_splits(lines)

    assert (splits.home.successes, splits.home.valid, splits.home.missing) == (1, 2, 0)
    assert (splits.away.successes, splits.away.valid, splits.away.missing) == (1, 1, 1)
    assert (splits.overall.successes, splits.overall.valid, splits.overall.missing) == (2, 3, 1)
    assert splits.home.percentage == 0.5
    assert splits.away.percentage == 1.0


def test_venue_split_deduplicates_records_before_calculating():
    duplicate = line(day=1, fixture_id=80, sot=1)
    splits = compute_venue_splits([duplicate, duplicate])

    assert splits.home.valid == 1


def test_single_venue_rate_includes_an_explanatory_qualifier():
    result = venue_rate([line(home=False, sot=1)], Venue.AWAY)

    assert result.qualifier == "away"
    assert "valid away starts" in result.describe()


def test_competition_split_reports_sample_average_and_display_label():
    lines = [
        line(day=1, competition_id=1, competition_name="Premier League", sot=1, shots=2),
        line(day=2, competition_id=1, competition_name="Premier League", sot=0, shots=4),
        line(day=3, competition_id=2, competition_name="FA Cup", sot=None, shots=None),
    ]

    entries = compute_competition_split(lines)
    premier_league = next(entry for entry in entries if entry.key == 1)
    fa_cup = next(entry for entry in entries if entry.key == 2)

    assert premier_league.label == "Premier League"
    assert premier_league.total_starts == 2
    assert premier_league.rate.percentage == 0.5
    assert premier_league.average_sot == 0.5
    assert premier_league.average_shots == 3.0
    assert fa_cup.rate.percentage is None
    assert fa_cup.average_sot is None


def test_grouped_split_uses_rate_then_sample_then_alphabetical_label_order():
    lines = [
        line(day=1, opponent_id=21, opponent_name="Zulu", sot=1),
        line(day=2, opponent_id=21, opponent_name="Zulu", sot=0),
        line(day=3, opponent_id=22, opponent_name="Alpha", sot=1),
        line(day=4, opponent_id=22, opponent_name="Alpha", sot=0),
        line(day=5, opponent_id=23, opponent_name="Top", sot=1),
    ]

    entries = compute_opponent_split(lines)

    assert [entry.label for entry in entries] == ["Top", "Alpha", "Zulu"]


def test_minimum_starts_filters_groups_without_hiding_the_sample_size():
    lines = [
        line(day=1, opponent_id=21),
        line(day=2, opponent_id=21),
        line(day=3, opponent_id=22),
    ]

    entries = compute_opponent_split(lines, minimum_starts=2)

    assert [entry.key for entry in entries] == [21]
    assert entries[0].total_starts == 2


def test_competition_opponent_and_season_splits_have_stable_fallback_labels():
    match = line(competition_id=4, opponent_id=24, season_id=2025)

    assert compute_competition_split([match])[0].label == "Competition 4"
    assert compute_opponent_split([match])[0].label == "Team 24"
    assert compute_season_split([match])[0].label == "Season 2025"


def test_generic_grouped_split_supports_typed_custom_dimensions():
    lines = [line(day=1, team_id=10), line(day=2, team_id=10)]

    entries = compute_grouped_split(
        lines,
        key_fn=lambda match: match.team_id,
        label_fn=lambda match: match.team_name or "Current team",
    )

    assert len(entries) == 1
    assert entries[0].key == 10


def test_position_share_uses_all_starts_and_ignores_substitute_appearances():
    lines = [
        line(day=1, position="ST"),
        line(day=2, position="ST"),
        line(day=3, position=None),
        line(day=4, position="RW", started=False),
    ]

    assert compute_position_share(lines) == pytest.approx(2 / 3)
    assert compute_position_share([line(position=None)]) is None


@pytest.mark.parametrize(
    "call",
    [
        lambda: compute_venue_splits([], threshold=0),
        lambda: compute_opponent_split([], minimum_starts=0),
        lambda: compute_season_split([], threshold=-1),
    ],
)
def test_split_parameters_are_validated_even_for_empty_inputs(call):
    with pytest.raises(ValueError, match="positive integer"):
        call()
