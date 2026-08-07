"""Pure analytics engine.

**No database, HTTP or provider imports are permitted in this package.**
Everything here takes typed value objects and returns typed results, which is
what makes the full matrix of awkward cases - no matches, all data missing, a
streak ending in failure, duplicate records - testable without a database.
``tests/test_analytics_purity.py`` enforces the rule.
"""

from __future__ import annotations

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
from app.analytics.form import (
    FormComparison,
    build_sot_trend,
    compare_recent_to_baseline,
    compute_form_window,
    compute_form_windows,
)
from app.analytics.math import (
    mean,
    per_90,
    safe_divide,
    safe_rate,
    wilson_lower_bound,
)
from app.analytics.models import (
    FormWindow,
    MatchStatLine,
    MinutesProfile,
    RateResult,
    SotSummary,
    SplitEntry,
    StreakSummary,
    VenueSplits,
)
from app.analytics.rules import (
    has_usable_sot,
    is_early_exit,
    meets_threshold,
    require_positive_integer,
    shot_accuracy,
)
from app.analytics.splits import (
    compute_competition_split,
    compute_grouped_split,
    compute_opponent_split,
    compute_position_share,
    compute_season_split,
    compute_venue_splits,
    venue_rate,
)
from app.analytics.streaks import compute_streaks
from app.analytics.summary import (
    DEFAULT_THRESHOLDS,
    build_sot_summary,
    compute_minutes_profile,
    compute_threshold_rate,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "FormComparison",
    "FormWindow",
    "MatchStatLine",
    "MinutesProfile",
    "RateResult",
    "SotSummary",
    "SplitEntry",
    "StreakSummary",
    "VenueSplits",
    "build_sot_summary",
    "build_sot_trend",
    "compare_recent_to_baseline",
    "compute_competition_split",
    "compute_form_window",
    "compute_form_windows",
    "compute_grouped_split",
    "compute_minutes_profile",
    "compute_opponent_split",
    "compute_position_share",
    "compute_season_split",
    "compute_streaks",
    "compute_threshold_rate",
    "compute_venue_splits",
    "deduplicate",
    "has_usable_sot",
    "is_early_exit",
    "last_n",
    "mean",
    "meets_threshold",
    "order_newest_first",
    "per_90",
    "require_positive_integer",
    "safe_divide",
    "safe_rate",
    "select_starts",
    "select_substitute_appearances",
    "select_venue",
    "shot_accuracy",
    "venue_rate",
    "wilson_lower_bound",
    "with_usable_sot",
    "without_usable_sot",
]
