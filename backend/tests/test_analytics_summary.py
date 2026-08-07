"""SOT summary calculations, including every edge case named in the spec."""

from __future__ import annotations

import pytest

from app.analytics.models import RateResult
from app.analytics.summary import build_sot_summary, compute_threshold_rate
from app.core.enums import DataQualityStatus
from tests.analytics_builders import line, series


class TestEmptyAndMinimalSamples:
    def test_no_matches_produces_zeroed_counts_and_null_rates(self):
        summary = build_sot_summary([], player_id=1)

        assert summary.total_appearances == 0
        assert summary.total_starts == 0
        # The critical assertion: a percentage of None, never 0.0.
        assert summary.rate_for(1).percentage is None
        assert summary.average_sot_per_start is None
        assert summary.shots_per_90 is None
        assert summary.shot_accuracy is None
        assert summary.has_any_valid_start is False

    def test_one_match(self):
        summary = build_sot_summary([line(sot=2, shots=4, minutes=90)])

        assert summary.total_starts == 1
        assert summary.rate_for(1).percentage == 1.0
        assert summary.rate_for(2).percentage == 1.0
        assert summary.rate_for(3).percentage == 0.0
        assert summary.average_sot_per_start == 2.0
        assert summary.shot_accuracy == 0.5
        assert summary.has_any_valid_start is True

    def test_all_successes(self):
        summary = build_sot_summary(series([1, 2, 3, 1, 2]))
        rate = summary.rate_for(1)
        assert (rate.successes, rate.valid, rate.missing) == (5, 5, 0)
        assert rate.percentage == 1.0

    def test_all_failures(self):
        summary = build_sot_summary(series([0, 0, 0]))
        rate = summary.rate_for(1)
        assert (rate.successes, rate.valid) == (0, 3)
        # A real, evidenced zero - distinct from the None of an empty sample.
        assert rate.percentage == 0.0


class TestMissingData:
    def test_missing_sot_is_excluded_from_the_denominator(self):
        """The central rule: unreported is not zero."""
        rate = compute_threshold_rate(series([1, 1, None, None, 0]), 1)

        assert rate.valid == 3
        assert rate.missing == 2
        assert rate.successes == 2
        assert rate.percentage == pytest.approx(2 / 3)

    def test_missing_sot_never_counts_as_a_failure(self):
        """If it counted as a failure the rate would be 2/5 = 40%, not 100%."""
        rate = compute_threshold_rate(series([1, 1, None, None, None]), 1)

        assert rate.percentage == 1.0
        assert rate.valid == 2
        assert rate.missing == 3

    def test_every_record_missing_gives_no_rate_at_all(self):
        rate = compute_threshold_rate(series([None, None, None]), 1)

        assert rate.valid == 0
        assert rate.missing == 3
        assert rate.percentage is None

    def test_untrusted_quality_status_is_excluded_even_with_a_value(self):
        """A provider_error row may carry a number, but not a reliable one."""
        rate = compute_threshold_rate(
            [
                line(day=1, sot=2),
                line(day=2, sot=3, quality=DataQualityStatus.PROVIDER_ERROR),
            ],
            1,
        )
        assert rate.valid == 1
        assert rate.missing == 1

    def test_manually_verified_records_are_trusted(self):
        rate = compute_threshold_rate([line(sot=1, quality=DataQualityStatus.MANUALLY_VERIFIED)], 1)
        assert rate.valid == 1
        assert rate.successes == 1

    def test_summary_reports_how_many_starts_lacked_sot(self):
        summary = build_sot_summary(series([1, None, None, 2]))
        assert summary.total_starts == 4
        assert summary.starts_missing_sot == 2


class TestSubstitutesAndStarts:
    def test_substitute_appearances_are_excluded_from_start_rates(self):
        lines = [
            line(day=1, sot=1, started=True),
            line(day=2, sot=0, started=True),
            # A hat-trick of SOT off the bench must not inflate the start rate.
            line(day=3, sot=3, started=False),
        ]
        summary = build_sot_summary(lines)

        assert summary.total_appearances == 3
        assert summary.total_starts == 2
        assert summary.substitute_appearances == 1
        assert summary.rate_for(1).valid == 2
        assert summary.rate_for(1).percentage == 0.5

    def test_a_squad_of_only_substitute_appearances_has_no_start_rate(self):
        summary = build_sot_summary(
            [line(day=1, sot=1, started=False), line(day=2, sot=2, started=False)]
        )
        assert summary.total_starts == 0
        assert summary.rate_for(1).percentage is None


class TestEarlyExits:
    def test_a_short_start_still_counts_as_a_start(self):
        """Spec: do not remove a start because the player played under 45."""
        summary = build_sot_summary(
            [line(day=1, sot=0, minutes=20), line(day=2, sot=2, minutes=90)]
        )

        assert summary.total_starts == 2
        assert summary.rate_for(1).valid == 2
        assert summary.rate_for(1).percentage == 0.5
        assert summary.minutes is not None
        assert summary.minutes.early_exits == 1

    def test_minutes_percentages_use_only_known_minutes(self):
        summary = build_sot_summary(
            [
                line(day=1, minutes=90),
                line(day=2, minutes=70),
                line(day=3, minutes=30),
                line(day=4, minutes=None),
            ]
        )
        profile = summary.minutes
        assert profile is not None
        assert profile.starts_considered == 4
        assert profile.starts_with_known_minutes == 3
        assert profile.pct_at_least_60 == pytest.approx(2 / 3)
        assert profile.pct_at_least_80 == pytest.approx(1 / 3)

    def test_no_known_minutes_yields_null_percentages(self):
        summary = build_sot_summary([line(minutes=None)])
        assert summary.minutes is not None
        assert summary.minutes.pct_at_least_60 is None
        assert summary.minutes.average_minutes_per_start is None


class TestDuplicates:
    def test_duplicate_records_are_counted_once(self):
        duplicate = line(day=1, sot=2, fixture_id=99)
        summary = build_sot_summary([duplicate, duplicate, line(day=2, sot=0, fixture_id=100)])

        assert summary.total_starts == 2
        assert summary.rate_for(1).valid == 2
        assert summary.rate_for(1).percentage == 0.5


class TestVolumeMetrics:
    def test_per_90_uses_only_matches_with_both_values_known(self):
        lines = [
            line(day=1, shots=4, sot=2, minutes=90),
            line(day=2, shots=2, sot=1, minutes=90),
            # No minutes recorded: contributes to totals but not to per-90.
            line(day=3, shots=6, sot=3, minutes=None),
        ]
        summary = build_sot_summary(lines)

        assert summary.total_shots == 12
        assert summary.total_shots_on_target == 6
        # 6 shots across 180 known minutes -> 3.0 per 90.
        assert summary.shots_per_90 == pytest.approx(3.0)
        assert summary.sot_per_90 == pytest.approx(1.5)

    def test_shot_accuracy(self):
        summary = build_sot_summary([line(day=1, shots=4, sot=2), line(day=2, shots=6, sot=1)])
        assert summary.shot_accuracy == pytest.approx(3 / 10)

    def test_zero_shots_gives_undefined_accuracy_not_zero(self):
        summary = build_sot_summary([line(shots=0, sot=0)])
        assert summary.shot_accuracy is None

    def test_team_sot_share(self):
        summary = build_sot_summary(
            [
                line(day=1, sot=2, team_shots_on_target=8),
                line(day=2, sot=1, team_shots_on_target=4),
            ]
        )
        assert summary.team_sot_share == pytest.approx(3 / 12)

    def test_team_share_is_none_without_team_data(self):
        assert build_sot_summary([line(sot=2)]).team_sot_share is None


class TestThresholds:
    def test_higher_thresholds_are_stricter(self):
        summary = build_sot_summary(series([0, 1, 2, 3]))
        assert summary.rate_for(1).successes == 3
        assert summary.rate_for(2).successes == 2
        assert summary.rate_for(3).successes == 1

    def test_unrequested_threshold_returns_an_empty_result(self):
        summary = build_sot_summary(series([1, 2]))
        empty = summary.rate_for(9)
        assert empty.valid == 0
        assert empty.percentage is None


class TestRateResultReporting:
    def test_describe_states_the_sample(self):
        assert (
            RateResult(8, 10, qualifier="away").describe()
            == "8 of 10 valid away starts recorded 1+ SOT: 80.0%"
        )

    def test_describe_reports_excluded_records(self):
        described = RateResult(8, 10, missing=2).describe()
        assert described == (
            "8 of 10 valid starts recorded 1+ SOT: 80.0%, with 2 additional starts missing SOT data"
        )

    def test_describe_pluralises_a_non_start_sample(self):
        assert (
            "1 additional appearance missing"
            in RateResult(1, 1, missing=1, noun="appearances").describe()
        )

    def test_describe_handles_an_empty_sample(self):
        assert RateResult(0, 0).describe() == "No valid starts with reported SOT data"
        assert "3 excluded" in RateResult(0, 0, missing=3).describe()

    def test_derived_counts(self):
        rate = RateResult(8, 10, missing=2)
        assert rate.failures == 2
        assert rate.total_considered == 12
        assert rate.has_sample is True
        assert RateResult(0, 0).has_sample is False
