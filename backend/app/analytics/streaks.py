"""Streak calculations over consecutive starts.

**How missing data is treated, and why.**

A start whose shots-on-target were never reported is *neutral*: it neither
extends nor breaks a streak.

The alternatives are both worse.  Treating it as a failure invents a zero the
provider never reported and would end a streak on no evidence.  Treating it as
a success inflates the streak on no evidence either.  Skipping it is the only
option that adds no information - but it does mean a streak can silently span
a gap, so every result reports ``missing_in_window`` and exposes
``is_reliable`` so the interface can qualify the number instead of presenting
it as clean.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.analytics.filters import deduplicate, order_newest_first, select_starts
from app.analytics.models import MatchStatLine, StreakSummary
from app.analytics.rules import has_usable_sot, meets_threshold, require_positive_integer


def _is_success(line: MatchStatLine, threshold: int) -> bool | None:
    """True / False / None (unknown) for one start against a threshold."""
    if not has_usable_sot(line.shots_on_target, line.data_quality_status):
        return None
    return meets_threshold(line.shots_on_target, threshold)


def compute_streaks(lines: Iterable[MatchStatLine], threshold: int = 1) -> StreakSummary:
    """Current and longest streaks of starts reaching ``threshold`` SOT.

    Only starts are considered; substitute appearances are ignored entirely
    rather than breaking a run of starts.

    >>> from datetime import UTC, datetime, timedelta
    >>> base = datetime(2025, 1, 1, tzinfo=UTC)
    >>> def line(i, sot):
    ...     return MatchStatLine(
    ...         fixture_id=i, player_id=1, team_id=1, opponent_id=2,
    ...         fixture_date=base + timedelta(days=i), competition_id=1,
    ...         season_id=1, home=True, started=True,
    ...         substitute_appearance=False, shots_on_target=sot,
    ...     )
    >>> s = compute_streaks([line(1, 1), line(2, 0), line(3, 2), line(4, 3)])
    >>> (s.current, s.longest)
    (2, 2)
    """
    require_positive_integer(threshold, name="threshold")
    starts = order_newest_first(select_starts(deduplicate(lines)))

    if not starts:
        return StreakSummary(
            threshold=threshold,
            current=0,
            longest=0,
            never_failed=False,
            starts_since_last_failure=0,
        )

    # --- Current streak: walk backwards from the most recent start ---------
    current = 0
    missing_in_window = 0
    for line in starts:
        outcome = _is_success(line, threshold)
        if outcome is None:
            missing_in_window += 1
            continue
        if outcome:
            current += 1
        else:
            break

    # --- Longest streak: walk forwards through history --------------------
    longest = 0
    run = 0
    for line in reversed(starts):
        outcome = _is_success(line, threshold)
        if outcome is None:
            continue
        if outcome:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # --- Most recent failure ----------------------------------------------
    last_failure: MatchStatLine | None = None
    starts_since_last_failure = 0
    for line in starts:
        if _is_success(line, threshold) is False:
            last_failure = line
            break
        # Counts every start after the failure, including neutral ones - the
        # player did start those matches.
        starts_since_last_failure += 1

    return StreakSummary(
        threshold=threshold,
        current=current,
        longest=longest,
        missing_in_window=missing_in_window,
        last_failure_date=last_failure.fixture_date if last_failure else None,
        last_failure_fixture_id=last_failure.fixture_id if last_failure else None,
        starts_since_last_failure=starts_since_last_failure,
        never_failed=last_failure is None,
    )
