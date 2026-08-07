"""Current streak, longest streak and latest zero-SOT tests."""

from __future__ import annotations

import pytest

from app.analytics.streaks import compute_streaks
from app.core.enums import DataQualityStatus
from tests.analytics_builders import line, series


def test_no_matches_has_no_streak_and_does_not_claim_never_failed():
    streak = compute_streaks([])

    assert streak.current == 0
    assert streak.longest == 0
    assert streak.last_failure_date is None
    assert streak.never_failed is False


def test_one_successful_start_creates_current_and_longest_streaks():
    streak = compute_streaks(series([1]))

    assert streak.current == 1
    assert streak.longest == 1
    assert streak.never_failed is True
    assert streak.starts_since_last_failure == 1


def test_current_and_longest_streaks_are_calculated_newest_first():
    streak = compute_streaks(series([1, 1, 0, 1, 1]))

    assert streak.current == 2
    assert streak.longest == 2
    assert streak.last_failure_fixture_id == 3
    assert streak.starts_since_last_failure == 2


def test_current_streak_ending_with_a_failure_is_zero():
    streak = compute_streaks(series([1, 1, 0]))

    assert streak.current == 0
    assert streak.longest == 2
    assert streak.last_failure_fixture_id == 3
    assert streak.starts_since_last_failure == 0


def test_all_failures_have_no_success_streak():
    streak = compute_streaks(series([0, 0, 0]))

    assert streak.current == 0
    assert streak.longest == 0
    assert streak.last_failure_fixture_id == 3
    assert streak.never_failed is False


def test_player_who_never_recorded_zero_has_no_latest_failure():
    streak = compute_streaks(series([1, 2, 1, 3]))

    assert streak.current == 4
    assert streak.longest == 4
    assert streak.last_failure_date is None
    assert streak.last_failure_fixture_id is None
    assert streak.starts_since_last_failure == 4
    assert streak.never_failed is True


def test_missing_data_is_neutral_but_marks_the_current_streak_unreliable():
    streak = compute_streaks(series([0, 1, None, 1]))

    assert streak.current == 2
    assert streak.longest == 2
    assert streak.missing_in_window == 1
    assert streak.starts_since_last_failure == 3
    assert streak.is_reliable is False


def test_missing_data_behind_the_latest_failure_does_not_caveat_current_zero():
    streak = compute_streaks(series([None, 1, 0]))

    assert streak.current == 0
    assert streak.missing_in_window == 0
    assert streak.is_reliable is True


def test_all_missing_starts_create_no_successes_and_are_clearly_unreliable():
    streak = compute_streaks(series([None, None]))

    assert streak.current == 0
    assert streak.longest == 0
    assert streak.missing_in_window == 2
    assert streak.never_failed is True
    assert streak.is_reliable is False


def test_untrusted_value_is_treated_as_missing_not_as_a_success():
    streak = compute_streaks(
        [
            line(day=1, sot=0),
            line(day=2, sot=3, quality=DataQualityStatus.PROVIDER_ERROR),
        ]
    )

    assert streak.current == 0
    assert streak.missing_in_window == 1
    assert streak.last_failure_fixture_id == 1


def test_substitute_appearances_do_not_extend_or_break_start_streaks():
    streak = compute_streaks(
        [
            line(day=1, sot=1),
            line(day=2, sot=0, started=False),
            line(day=3, sot=2),
        ]
    )

    assert streak.current == 2
    assert streak.longest == 2
    assert streak.never_failed is True


def test_duplicate_records_do_not_inflate_streaks():
    duplicate = line(day=2, fixture_id=70, sot=1)

    streak = compute_streaks([line(day=1, sot=1), duplicate, duplicate])

    assert streak.current == 2


def test_higher_thresholds_define_failure_relative_to_that_threshold():
    streak = compute_streaks(series([2, 1, 3]), threshold=2)

    assert streak.current == 1
    assert streak.longest == 1
    assert streak.last_failure_fixture_id == 2
    assert streak.starts_since_last_failure == 1


@pytest.mark.parametrize("threshold", [0, -1])
def test_streak_threshold_must_be_positive_even_with_no_matches(threshold: int):
    with pytest.raises(ValueError, match="positive integer"):
        compute_streaks([], threshold=threshold)
