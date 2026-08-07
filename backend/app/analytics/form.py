"""Recent-form calculations: last-N windows against season-long baselines."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.analytics.filters import deduplicate, last_n, order_newest_first, select_starts
from app.analytics.models import FormWindow, MatchStatLine, RateResult
from app.analytics.rules import require_positive_integer
from app.analytics.summary import compute_threshold_rate

#: Windows reported by default.
DEFAULT_WINDOWS: tuple[int, ...] = (5, 10, 20)


@dataclass(frozen=True, slots=True)
class FormComparison:
    """Recent form set against the full-sample baseline.

    ``delta`` is ``None`` whenever either side lacks a usable sample - the
    difference between an unknown and a known rate is not zero, it is unknown.
    """

    window: int
    recent: RateResult
    baseline: RateResult
    delta: float | None

    @property
    def is_comparable(self) -> bool:
        """False when either side has no valid starts behind it."""
        return self.recent.has_sample and self.baseline.has_sample

    def describe(self) -> str:
        if not self.is_comparable:
            return (
                f"Last {self.window}: {self.recent.describe()} (not comparable - insufficient data)"
            )
        assert self.delta is not None
        direction = "up" if self.delta > 0 else "down" if self.delta < 0 else "level"
        return (
            f"Last {self.window}: {self.recent.describe()} "
            f"vs {self.baseline.describe()} ({direction} {abs(self.delta) * 100:.1f} pts)"
        )


def compute_form_window(
    lines: Iterable[MatchStatLine], window: int, threshold: int = 1
) -> FormWindow:
    """Hit rate over the most recent ``window`` starts.

    The window counts **starts**, not calendar matches, and it is applied
    before the missing-SOT filter.  So "last 5 starts" always means the five
    most recent starts; if two of them lack SOT data the rate is reported as
    3 valid with 2 missing, rather than silently reaching further back to find
    five records that happen to have data.
    """
    require_positive_integer(window, name="window")
    require_positive_integer(threshold, name="threshold")
    starts = order_newest_first(select_starts(deduplicate(lines)))
    recent = last_n(starts, window)
    return FormWindow(
        window=window,
        rate=compute_threshold_rate(recent, threshold, qualifier=f"last {window}"),
        starts_available=len(recent),
    )


def compute_form_windows(
    lines: Iterable[MatchStatLine],
    windows: Sequence[int] = DEFAULT_WINDOWS,
    threshold: int = 1,
) -> dict[int, FormWindow]:
    """Hit rates for several windows at once."""
    for window in windows:
        require_positive_integer(window, name="window")
    require_positive_integer(threshold, name="threshold")
    material = list(lines)
    return {window: compute_form_window(material, window, threshold) for window in windows}


def compare_recent_to_baseline(
    lines: Iterable[MatchStatLine], window: int = 5, threshold: int = 1
) -> FormComparison:
    """Compare a recent window against the whole supplied sample.

    The baseline is every start provided, which normally means the season the
    caller filtered to. It deliberately includes the recent window: excluding
    it would make the two figures describe disjoint periods and invite
    over-reading of small differences.
    """
    require_positive_integer(window, name="window")
    require_positive_integer(threshold, name="threshold")
    starts = order_newest_first(select_starts(deduplicate(lines)))
    recent_rate = compute_threshold_rate(
        last_n(starts, window), threshold, qualifier=f"last {window}"
    )
    baseline_rate = compute_threshold_rate(starts, threshold, qualifier="all")

    recent_pct = recent_rate.percentage
    baseline_pct = baseline_rate.percentage
    delta = None if recent_pct is None or baseline_pct is None else recent_pct - baseline_pct

    return FormComparison(
        window=window,
        recent=recent_rate,
        baseline=baseline_rate,
        delta=delta,
    )


def build_sot_trend(
    lines: Iterable[MatchStatLine], *, window: int = 5, threshold: int = 1
) -> list[tuple[MatchStatLine, float | None]]:
    """Rolling hit rate over starts, oldest first, for charting.

    Each point is the rate across the ``window`` starts ending at that match.
    The rate is ``None`` where no start in the window has usable SOT data, so
    the chart can break the line instead of drawing through a gap.
    """
    require_positive_integer(window, name="window")
    require_positive_integer(threshold, name="threshold")
    starts = list(reversed(order_newest_first(select_starts(deduplicate(lines)))))

    points: list[tuple[MatchStatLine, float | None]] = []
    for index, line in enumerate(starts):
        chunk = starts[max(0, index - window + 1) : index + 1]
        points.append((line, compute_threshold_rate(chunk, threshold).percentage))
    return points
