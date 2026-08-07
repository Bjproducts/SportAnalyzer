"""Recent form, season comparison and trend-series tests."""

from __future__ import annotations

import pytest

from app.analytics.form import (
    build_sot_trend,
    compare_recent_to_baseline,
    compute_form_window,
    compute_form_windows,
)
from tests.analytics_builders import line, series


def test_last_five_is_based_on_the_five_most_recent_starts():
    lines = series([0, 1, 0, 1, 1, 0])
    lines.append(line(day=99, sot=3, started=False))

    form = compute_form_window(lines, 5)

    assert form.starts_available == 5
    assert (form.rate.successes, form.rate.valid, form.rate.missing) == (3, 5, 0)
    assert form.rate.percentage == 0.6


def test_last_ten_reports_the_smaller_available_sample_early_in_a_career():
    form = compute_form_window(series([1, 0, 1]), 10)

    assert form.window == 10
    assert form.starts_available == 3
    assert form.rate.valid == 3


def test_missing_sot_inside_a_window_is_not_backfilled_from_older_starts():
    lines = series([1, 1, 1, None, None, 0])

    form = compute_form_window(lines, 3)

    assert form.starts_available == 3
    assert (form.rate.successes, form.rate.valid, form.rate.missing) == (0, 1, 2)
    assert form.rate.percentage == 0.0


def test_default_form_windows_include_last_five_ten_and_twenty():
    windows = compute_form_windows(series([1, 0, 1]))

    assert set(windows) == {5, 10, 20}
    assert all(result.starts_available == 3 for result in windows.values())


def test_custom_form_windows_and_thresholds_are_supported():
    windows = compute_form_windows(series([1, 2, 3]), windows=(1, 2), threshold=2)

    assert windows[1].rate.percentage == 1.0
    assert windows[2].rate.successes == 2


def test_recent_form_comparison_reports_the_percentage_point_delta():
    comparison = compare_recent_to_baseline(series([0, 0, 0, 1, 1]), window=2)

    assert comparison.recent.percentage == 1.0
    assert comparison.baseline.percentage == 0.4
    assert comparison.delta == pytest.approx(0.6)
    assert comparison.is_comparable is True
    assert "up 60.0 pts" in comparison.describe()


def test_recent_form_comparison_is_unknown_when_sot_is_entirely_missing():
    comparison = compare_recent_to_baseline(series([None, None]), window=1)

    assert comparison.delta is None
    assert comparison.is_comparable is False
    assert "not comparable" in comparison.describe()


def test_trend_is_oldest_first_and_uses_a_rolling_start_window():
    points = build_sot_trend(series([1, 0, 1]), window=2)

    assert [match.fixture_id for match, _ in points] == [1, 2, 3]
    assert [rate for _, rate in points] == [1.0, 0.5, 0.5]


def test_trend_breaks_when_a_window_has_no_usable_sot_data():
    points = build_sot_trend(series([None, None, 1]), window=2)

    assert [rate for _, rate in points] == [None, None, 1.0]


def test_form_functions_deduplicate_before_selecting_the_recent_window():
    duplicate = line(day=3, fixture_id=50, sot=1)
    form = compute_form_window([line(day=1, sot=0), duplicate, duplicate], 2)

    assert form.starts_available == 2
    assert form.rate.valid == 2


@pytest.mark.parametrize(
    "call",
    [
        lambda: compute_form_window([], 0),
        lambda: compute_form_windows([], windows=(5, -1)),
        lambda: compare_recent_to_baseline([], threshold=0),
        lambda: build_sot_trend([], window=0),
    ],
)
def test_form_parameters_are_validated_even_for_empty_inputs(call):
    with pytest.raises(ValueError, match="positive integer"):
        call()
