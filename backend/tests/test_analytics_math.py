"""Numeric primitives: safe division and the Wilson bound."""

from __future__ import annotations

import pytest

from app.analytics.math import (
    mean,
    per_90,
    round_or_none,
    safe_divide,
    safe_rate,
    wilson_lower_bound,
)


class TestSafeDivision:
    def test_normal_division(self):
        assert safe_divide(3, 4) == 0.75

    def test_zero_numerator_is_a_real_zero(self):
        assert safe_divide(0, 4) == 0.0

    @pytest.mark.parametrize(
        ("numerator", "denominator"),
        [(3, 0), (0, 0), (None, 4), (3, None), (None, None)],
    )
    def test_undefined_division_returns_none_not_zero(self, numerator, denominator):
        """0.0 would assert a fact the data does not support."""
        assert safe_divide(numerator, denominator) is None

    def test_safe_rate_distinguishes_no_successes_from_no_sample(self):
        assert safe_rate(0, 5) == 0.0
        assert safe_rate(0, 0) is None

    def test_division_never_raises(self):
        for denominator in (0, None, 0.0):
            assert safe_divide(1, denominator) is None


class TestPer90:
    def test_scales_to_ninety_minutes(self):
        assert per_90(4, 180) == 2.0
        assert per_90(1, 45) == 2.0

    @pytest.mark.parametrize("minutes", [0, None, -10])
    def test_returns_none_without_usable_minutes(self, minutes):
        assert per_90(4, minutes) is None


class TestWilsonLowerBound:
    def test_the_ranking_rule_from_the_specification(self):
        """A perfect 2/2 must not outrank a solid 18/20."""
        tiny_perfect = wilson_lower_bound(2, 2)
        large_strong = wilson_lower_bound(18, 20)

        assert tiny_perfect is not None and large_strong is not None
        assert large_strong > tiny_perfect
        assert round(tiny_perfect, 3) == 0.342
        assert round(large_strong, 3) == 0.699

    def test_bound_is_never_above_the_observed_rate(self):
        for successes, trials in [(1, 1), (5, 10), (18, 20), (99, 100), (0, 7)]:
            bound = wilson_lower_bound(successes, trials)
            assert bound is not None
            assert 0.0 <= bound <= successes / trials + 1e-9

    def test_bound_rises_with_sample_size_at_a_fixed_rate(self):
        bounds = [wilson_lower_bound(int(0.8 * n), n) for n in (5, 10, 50, 200)]
        assert all(b is not None for b in bounds)
        assert bounds == sorted(bounds)  # type: ignore[type-var]

    def test_no_trials_returns_none(self):
        assert wilson_lower_bound(0, 0) is None

    def test_zero_successes_gives_a_zero_bound(self):
        assert wilson_lower_bound(0, 10) == 0.0

    def test_impossible_input_is_rejected_loudly(self):
        with pytest.raises(ValueError, match="within"):
            wilson_lower_bound(5, 2)


class TestMean:
    def test_mean_of_values(self):
        assert mean([1, 2, 3]) == 2.0

    def test_empty_returns_none(self):
        assert mean([]) is None

    def test_presentation_rounding_preserves_missing_values(self):
        assert round_or_none(1 / 3, 2) == 0.33
        assert round_or_none(None, 2) is None
