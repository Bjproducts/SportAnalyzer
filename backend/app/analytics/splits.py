"""Venue, competition and opponent splits."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from app.analytics.filters import (
    deduplicate,
    select_starts,
    select_venue,
    with_usable_sot,
)
from app.analytics.math import mean, safe_divide
from app.analytics.models import MatchStatLine, RateResult, SplitEntry, VenueSplits
from app.analytics.rules import require_positive_integer
from app.analytics.summary import compute_threshold_rate
from app.core.enums import Venue


def compute_venue_splits(lines: Iterable[MatchStatLine], threshold: int = 1) -> VenueSplits:
    """Home / away / combined hit rates across starts.

    Home and away are reported separately because they are not interchangeable:
    shot volume, and therefore SOT opportunity, differs systematically by venue.

    Each rate carries its own valid/missing counts, so an away split built from
    three starts can never be mistaken for one built from thirty.
    """
    require_positive_integer(threshold, name="threshold")
    starts = select_starts(deduplicate(lines))

    return VenueSplits(
        home=compute_threshold_rate(select_venue(starts, Venue.HOME), threshold, qualifier="home"),
        away=compute_threshold_rate(select_venue(starts, Venue.AWAY), threshold, qualifier="away"),
        overall=compute_threshold_rate(starts, threshold),
    )


def _build_entry(
    key: str | int,
    label: str,
    group: list[MatchStatLine],
    threshold: int,
) -> SplitEntry:
    with_sot = with_usable_sot(group)
    return SplitEntry(
        key=key,
        label=label,
        rate=compute_threshold_rate(group, threshold),
        average_sot=mean([line.shots_on_target or 0 for line in with_sot]),
        average_shots=mean([line.shots for line in group if line.shots is not None]),
        total_starts=len(group),
    )


def compute_grouped_split(
    lines: Iterable[MatchStatLine],
    key_fn: Callable[[MatchStatLine], str | int],
    label_fn: Callable[[MatchStatLine], str],
    *,
    threshold: int = 1,
    minimum_starts: int = 1,
) -> list[SplitEntry]:
    """Generic categorical split over starts.

    Results are ordered by hit rate descending, then by sample size, then by
    label - so ties resolve deterministically and a larger sample wins.
    Groups are ordered but **not** filtered by rate: ``minimum_starts`` is the
    only exclusion, and it defaults to showing everything.
    """
    require_positive_integer(threshold, name="threshold")
    require_positive_integer(minimum_starts, name="minimum_starts")
    starts = select_starts(deduplicate(lines))

    groups: dict[str | int, list[MatchStatLine]] = {}
    labels: dict[str | int, str] = {}
    for line in starts:
        key = key_fn(line)
        groups.setdefault(key, []).append(line)
        labels.setdefault(key, label_fn(line))

    entries = [
        _build_entry(key, labels[key], group, threshold)
        for key, group in groups.items()
        if len(group) >= minimum_starts
    ]

    # `percentage` is None for groups with no usable SOT; sort those last
    # rather than letting None compare against floats.
    entries.sort(
        key=lambda entry: (
            -(entry.rate.percentage if entry.rate.percentage is not None else -1.0),
            -entry.rate.valid,
            entry.label.casefold(),
        )
    )
    return entries


def compute_competition_split(
    lines: Iterable[MatchStatLine], *, threshold: int = 1, minimum_starts: int = 1
) -> list[SplitEntry]:
    """Hit rate per competition."""
    return compute_grouped_split(
        lines,
        key_fn=lambda line: line.competition_id,
        label_fn=lambda line: line.competition_name or f"Competition {line.competition_id}",
        threshold=threshold,
        minimum_starts=minimum_starts,
    )


def compute_opponent_split(
    lines: Iterable[MatchStatLine], *, threshold: int = 1, minimum_starts: int = 1
) -> list[SplitEntry]:
    """Hit rate per opponent.

    Opponent samples are usually tiny (two matches a season in a league), so
    ``minimum_starts`` matters more here than anywhere else. The caller is
    responsible for setting it; the default shows every opponent, sample size
    attached.
    """
    return compute_grouped_split(
        lines,
        key_fn=lambda line: line.opponent_id,
        label_fn=lambda line: line.opponent_name or f"Team {line.opponent_id}",
        threshold=threshold,
        minimum_starts=minimum_starts,
    )


def compute_season_split(
    lines: Iterable[MatchStatLine], *, threshold: int = 1, minimum_starts: int = 1
) -> list[SplitEntry]:
    """Hit rate per season."""
    return compute_grouped_split(
        lines,
        key_fn=lambda line: line.season_id,
        label_fn=lambda line: line.season_label or f"Season {line.season_id}",
        threshold=threshold,
        minimum_starts=minimum_starts,
    )


def compute_position_share(lines: Iterable[MatchStatLine]) -> float | None:
    """Share of starts the player took in their most common position."""
    starts = select_starts(deduplicate(lines))
    positions = [line.position for line in starts if line.position]
    if not positions:
        return None
    most_common = max(set(positions), key=positions.count)
    return safe_divide(positions.count(most_common), len(starts))


def venue_rate(lines: Iterable[MatchStatLine], venue: Venue, threshold: int = 1) -> RateResult:
    """Hit rate for a single venue."""
    starts = select_starts(deduplicate(lines))
    qualifier = None if venue is Venue.ALL else venue.value
    return compute_threshold_rate(select_venue(starts, venue), threshold, qualifier=qualifier)
