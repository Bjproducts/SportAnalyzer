"""Selection and ordering helpers for match-stat sequences.

Pure list operations - no database access.  The repository layer is expected to
have already applied coarse filters (competition, season, date range, and the
"competitive matches only" default) in SQL; these helpers handle the
fine-grained selection the analytics functions need.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.analytics.models import MatchStatLine
from app.analytics.rules import has_usable_sot
from app.core.enums import Venue


def order_newest_first(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Sort matches newest first.

    ``fixture_id`` breaks ties so the ordering is deterministic when two
    matches kick off at the same instant - without it, "last 5" could return
    different sets on successive calls.
    """
    return sorted(lines, key=lambda line: (line.fixture_date, line.fixture_id), reverse=True)


def select_starts(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Only matches the player started.

    A start is kept regardless of how few minutes it lasted; short starts are
    flagged as early exits, never dropped.
    """
    return [line for line in lines if line.started]


def select_substitute_appearances(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Only appearances from the bench."""
    return [line for line in lines if line.substitute_appearance and not line.started]


def select_venue(lines: Iterable[MatchStatLine], venue: Venue) -> list[MatchStatLine]:
    """Restrict to home, away, or everything."""
    if venue is Venue.ALL:
        return list(lines)
    want_home = venue is Venue.HOME
    return [line for line in lines if line.home is want_home]


def with_usable_sot(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Only records whose shots-on-target value may be counted."""
    return [
        line for line in lines if has_usable_sot(line.shots_on_target, line.data_quality_status)
    ]


def without_usable_sot(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Only records excluded from rate calculations for missing/untrusted SOT."""
    return [
        line for line in lines if not has_usable_sot(line.shots_on_target, line.data_quality_status)
    ]


def last_n(lines: Sequence[MatchStatLine], n: int) -> list[MatchStatLine]:
    """The ``n`` most recent matches.

    Sorts defensively rather than trusting the caller's ordering: silently
    returning the *oldest* n would be a subtle and very damaging bug.
    """
    if n <= 0:
        return []
    return order_newest_first(lines)[:n]


def deduplicate(lines: Iterable[MatchStatLine]) -> list[MatchStatLine]:
    """Drop duplicate ``(fixture, player, team)`` records, keeping the first.

    The database's unique constraint should make this unnecessary. It exists
    because a duplicate reaching a rate calculation would silently double-count
    one match, and a cheap guard is worth more than an assumption.
    """
    seen: set[tuple[int, int, int]] = set()
    unique: list[MatchStatLine] = []
    for line in lines:
        key = (line.fixture_id, line.player_id, line.team_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)
    return unique
