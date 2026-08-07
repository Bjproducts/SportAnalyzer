"""Shots-on-target summary calculations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.analytics.filters import (
    deduplicate,
    select_starts,
    select_substitute_appearances,
    with_usable_sot,
)
from app.analytics.math import mean, per_90, safe_divide
from app.analytics.models import MatchStatLine, MinutesProfile, RateResult, SotSummary
from app.analytics.rules import has_usable_sot, meets_threshold, require_positive_integer

#: Thresholds reported by default: "at least 1/2/3 shots on target".
DEFAULT_THRESHOLDS: tuple[int, ...] = (1, 2, 3)


def compute_threshold_rate(
    starts: Iterable[MatchStatLine],
    threshold: int,
    *,
    qualifier: str | None = None,
    noun: str = "starts",
) -> RateResult:
    """Hit rate for "at least ``threshold`` shots on target" across starts.

    Records whose SOT is unreported are excluded from the denominator and
    counted in ``missing`` - they are not evidence of failure.  This is the
    single most important behaviour in the engine.

    >>> from datetime import UTC, datetime
    >>> def line(sot):
    ...     return MatchStatLine(
    ...         fixture_id=1, player_id=1, team_id=1, opponent_id=2,
    ...         fixture_date=datetime(2025, 1, 1, tzinfo=UTC),
    ...         competition_id=1, season_id=1, home=True, started=True,
    ...         substitute_appearance=False, shots_on_target=sot,
    ...     )
    >>> rate = compute_threshold_rate([line(2), line(0), line(None)], 1)
    >>> (rate.successes, rate.valid, rate.missing)
    (1, 2, 1)
    """
    require_positive_integer(threshold, name="threshold")
    successes = 0
    valid = 0
    missing = 0

    for line in starts:
        if not has_usable_sot(line.shots_on_target, line.data_quality_status):
            missing += 1
            continue
        valid += 1
        if meets_threshold(line.shots_on_target, threshold):
            successes += 1

    return RateResult(
        successes=successes,
        valid=valid,
        missing=missing,
        noun=noun,
        qualifier=qualifier,
        criterion=f"{threshold}+ SOT",
    )


def compute_minutes_profile(
    starts: Sequence[MatchStatLine],
    *,
    early_exit_threshold: int = 45,
) -> MinutesProfile:
    """Minutes-played profile across starts.

    Percentages use only starts with a *known* minutes value as the
    denominator, so an unreported figure cannot masquerade as "did not reach
    60 minutes".
    """
    require_positive_integer(early_exit_threshold, name="early_exit_threshold")
    known = [line for line in starts if line.minutes_played is not None]
    minutes = [line.minutes_played for line in known if line.minutes_played is not None]

    at_least_60 = sum(1 for value in minutes if value >= 60)
    at_least_80 = sum(1 for value in minutes if value >= 80)
    early_exits = sum(1 for value in minutes if value < early_exit_threshold)

    return MinutesProfile(
        starts_considered=len(starts),
        starts_with_known_minutes=len(known),
        pct_at_least_60=safe_divide(at_least_60, len(known)),
        pct_at_least_80=safe_divide(at_least_80, len(known)),
        early_exits=early_exits,
        average_minutes_per_start=mean(minutes),
        total_minutes=sum(minutes),
    )


def build_sot_summary(
    lines: Iterable[MatchStatLine],
    *,
    player_id: int | None = None,
    thresholds: Sequence[int] = DEFAULT_THRESHOLDS,
    qualifier: str | None = None,
    early_exit_threshold: int = 45,
) -> SotSummary:
    """Build the full shots-on-target profile for one player.

    All threshold rates are computed over **starts only**; substitute
    appearances are counted and reported separately but never enter a
    start-based denominator.

    Volume figures are each computed over the records that actually have the
    value in question:

    * ``total_shots`` sums starts with a reported shot count.
    * ``total_shots_on_target`` sums starts with a usable SOT value.
    * The per-90 figures use only starts where *both* the statistic and the
      minutes are known, so numerator and denominator always describe the same
      set of matches.
    """
    unique = deduplicate(lines)

    for threshold in thresholds:
        require_positive_integer(threshold, name="threshold")
    require_positive_integer(early_exit_threshold, name="early_exit_threshold")

    player_ids = {line.player_id for line in unique}
    if len(player_ids) > 1:
        raise ValueError("A SOT summary can only contain one player.")

    if player_id is None:
        player_id = unique[0].player_id if unique else 0
    elif player_ids and player_id not in player_ids:
        raise ValueError("player_id does not match the supplied match records.")

    starts = select_starts(unique)
    substitutes = select_substitute_appearances(unique)

    threshold_rates = {
        threshold: compute_threshold_rate(starts, threshold, qualifier=qualifier)
        for threshold in thresholds
    }

    starts_with_shots = [line for line in starts if line.shots is not None]
    starts_with_sot = with_usable_sot(starts)

    total_shots = sum(line.shots or 0 for line in starts_with_shots)
    total_sot = sum(line.shots_on_target or 0 for line in starts_with_sot)

    # Per-90 denominators are restricted to matches that contributed to the
    # numerator; mixing in minutes from matches with no reported shots would
    # deflate the rate.
    shot_minutes = sum(
        line.minutes_played or 0 for line in starts_with_shots if line.minutes_played is not None
    )
    shot_total_for_90 = sum(
        line.shots or 0 for line in starts_with_shots if line.minutes_played is not None
    )
    sot_minutes = sum(
        line.minutes_played or 0 for line in starts_with_sot if line.minutes_played is not None
    )
    sot_total_for_90 = sum(
        line.shots_on_target or 0 for line in starts_with_sot if line.minutes_played is not None
    )

    # Team share: only starts where both the player's and the team's SOT are
    # known, otherwise the ratio compares incomparable sets.
    shareable = [
        line
        for line in starts_with_sot
        if line.team_shots_on_target is not None and line.team_shots_on_target > 0
    ]
    team_sot_share = safe_divide(
        sum(line.shots_on_target or 0 for line in shareable),
        sum(line.team_shots_on_target or 0 for line in shareable),
    )

    return SotSummary(
        player_id=player_id,
        total_appearances=len(unique),
        total_starts=len(starts),
        substitute_appearances=len(substitutes),
        threshold_rates=threshold_rates,
        total_shots=total_shots,
        total_shots_on_target=total_sot,
        starts_missing_sot=len(starts) - len(starts_with_sot),
        average_shots_per_start=safe_divide(total_shots, len(starts_with_shots)),
        average_sot_per_start=safe_divide(total_sot, len(starts_with_sot)),
        shots_per_90=per_90(shot_total_for_90, shot_minutes),
        sot_per_90=per_90(sot_total_for_90, sot_minutes),
        # Accuracy compares SOT to shots over the matches where both are known.
        shot_accuracy=safe_divide(
            sum(line.shots_on_target or 0 for line in starts_with_sot if line.shots is not None),
            sum(line.shots or 0 for line in starts_with_sot if line.shots is not None),
        ),
        team_sot_share=team_sot_share,
        minutes=compute_minutes_profile(starts, early_exit_threshold=early_exit_threshold),
    )
