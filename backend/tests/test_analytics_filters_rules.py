"""Low-level analytics selection and domain-rule tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.analytics.filters import (
    deduplicate,
    last_n,
    order_newest_first,
    select_starts,
    select_substitute_appearances,
    select_venue,
    with_usable_sot,
    without_usable_sot,
)
from app.analytics.rules import (
    has_usable_sot,
    is_early_exit,
    meets_threshold,
    require_positive_integer,
    shot_accuracy,
)
from app.core.enums import DataQualityStatus, Venue
from tests.analytics_builders import line


def test_ordering_is_newest_first_and_uses_fixture_id_to_break_ties():
    kickoff = datetime(2025, 1, 2, tzinfo=UTC)
    lines = [
        line(day=1, fixture_id=2, fixture_date=kickoff),
        line(day=3, fixture_id=3),
        line(day=1, fixture_id=1, fixture_date=kickoff),
    ]

    assert [item.fixture_id for item in order_newest_first(lines)] == [3, 2, 1]


def test_start_selection_keeps_short_starts_and_excludes_substitutes():
    short_start = line(day=1, minutes=12)
    substitute = line(day=2, started=False, minutes=30)

    assert select_starts([short_start, substitute]) == [short_start]
    assert select_substitute_appearances([short_start, substitute]) == [substitute]


def test_substitute_selection_requires_an_explicit_substitute_appearance():
    unknown_appearance = line(
        started=False,
        substitute_appearance=False,
        quality=DataQualityStatus.MISSING_LINEUP,
    )

    assert select_substitute_appearances([unknown_appearance]) == []


@pytest.mark.parametrize(
    ("venue", "expected_ids"),
    [(Venue.HOME, [1]), (Venue.AWAY, [2]), (Venue.ALL, [1, 2])],
)
def test_venue_selection(venue: Venue, expected_ids: list[int]):
    lines = [line(day=1, home=True), line(day=2, home=False)]

    assert [item.fixture_id for item in select_venue(lines, venue)] == expected_ids


def test_usable_sot_filters_consider_both_value_and_quality_status():
    lines = [
        line(day=1, sot=0),
        line(day=2, sot=1, quality=DataQualityStatus.PARTIAL),
        line(day=3, sot=None),
        line(day=4, sot=2, quality=DataQualityStatus.PROVIDER_ERROR),
    ]

    assert [item.fixture_id for item in with_usable_sot(lines)] == [1, 2]
    assert [item.fixture_id for item in without_usable_sot(lines)] == [3, 4]


def test_last_n_sorts_defensively_and_does_not_mutate_the_input():
    lines = [line(day=1), line(day=3), line(day=2)]

    assert [item.fixture_id for item in last_n(lines, 2)] == [3, 2]
    assert [item.fixture_id for item in lines] == [1, 3, 2]
    assert last_n(lines, 0) == []


def test_deduplicate_uses_the_required_composite_key_and_keeps_first_record():
    first = line(day=1, fixture_id=50, sot=1)
    conflicting_duplicate = line(day=2, fixture_id=50, sot=3)
    other_player = line(day=3, fixture_id=50, player_id=2)

    unique = deduplicate([first, conflicting_duplicate, other_player])

    assert unique == [first, other_player]


@pytest.mark.parametrize(
    ("started", "minutes", "expected"),
    [(True, 44, True), (True, 45, False), (True, None, None), (False, 10, False)],
)
def test_early_exit_boundary(started: bool, minutes: int | None, expected: bool | None):
    assert is_early_exit(started=started, minutes_played=minutes) is expected


@pytest.mark.parametrize("value", [0, -1, True])
def test_positive_integer_rule_rejects_invalid_domain_parameters(value: int):
    with pytest.raises(ValueError, match="positive integer"):
        require_positive_integer(value, name="window")


@pytest.mark.parametrize(
    ("sot", "quality", "expected"),
    [
        (0, DataQualityStatus.COMPLETE, True),
        (2, DataQualityStatus.MANUALLY_VERIFIED, True),
        (1, DataQualityStatus.PARTIAL, True),
        (None, DataQualityStatus.COMPLETE, False),
        (2, DataQualityStatus.MISSING_SOT, False),
        (2, DataQualityStatus.MISSING_LINEUP, False),
        (2, DataQualityStatus.PROVIDER_ERROR, False),
    ],
)
def test_sot_quality_rule(sot: int | None, quality: DataQualityStatus, expected: bool):
    assert has_usable_sot(sot, quality) is expected


def test_sot_value_is_usable_when_a_source_has_no_quality_classification():
    assert has_usable_sot(0, None) is True


def test_threshold_result_preserves_unknown_instead_of_calling_it_a_failure():
    assert meets_threshold(2, 2) is True
    assert meets_threshold(1, 2) is False
    assert meets_threshold(None, 2) is None


def test_threshold_rule_rejects_non_positive_thresholds_even_for_missing_data():
    with pytest.raises(ValueError, match="threshold"):
        meets_threshold(None, 0)


@pytest.mark.parametrize(
    ("shots", "sot", "expected"),
    [(4, 2, 0.5), (3, 0, 0.0), (0, 0, None), (None, 1, None), (2, None, None)],
)
def test_shot_accuracy_rule(shots: int | None, sot: int | None, expected: float | None):
    assert shot_accuracy(shots, sot) == expected
