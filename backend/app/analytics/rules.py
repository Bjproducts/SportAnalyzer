"""Pure domain rules shared by ingestion, analytics and the API.

Every rule here has exactly one definition.  ``early_exit``, for example, is
stored as a column *and* recomputed during analysis; both paths call
:func:`is_early_exit` so the two can never disagree.

This module imports nothing but the standard library and
:mod:`app.core.enums`, which keeps the analytics package free of SQLAlchemy.
"""

from __future__ import annotations

from app.core.enums import SOT_TRUSTWORTHY_STATUSES, DataQualityStatus

#: A start shorter than this is flagged as an early exit.  It is *still a
#: start* and still counts in every start-based denominator - the flag exists
#: to explain a low shot count, not to discard the match.
DEFAULT_EARLY_EXIT_MINUTES = 45


def require_positive_integer(value: int, *, name: str) -> int:
    """Return ``value`` when it is a positive integer, otherwise fail loudly.

    Analytics functions are also called outside the HTTP layer (tests, jobs and
    future CLI imports), so they cannot rely on API validation to protect domain
    invariants such as a positive streak threshold or form window.
    """
    if isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def is_early_exit(
    *,
    started: bool,
    minutes_played: int | None,
    threshold: int = DEFAULT_EARLY_EXIT_MINUTES,
) -> bool | None:
    """Was this a start that ended unusually early?

    Returns ``None`` when the answer is unknowable (a start with no recorded
    minutes).  ``False`` would assert the player saw out the match, which the
    data does not support.

    >>> is_early_exit(started=True, minutes_played=30)
    True
    >>> is_early_exit(started=True, minutes_played=90)
    False
    >>> is_early_exit(started=False, minutes_played=10)
    False
    >>> is_early_exit(started=True, minutes_played=None) is None
    True
    """
    require_positive_integer(threshold, name="threshold")
    if not started:
        # Only starts can exit early; a substitute's short outing is normal.
        return False
    if minutes_played is None:
        return None
    return minutes_played < threshold


def has_usable_sot(
    shots_on_target: int | None,
    data_quality_status: DataQualityStatus | None = None,
) -> bool:
    """May this record contribute to a shots-on-target rate?

    Two independent gates, both of which must pass:

    1. The value is present.  ``None`` means the provider did not report it,
       which is not evidence of zero and must never be counted as a failure.
    2. The record's quality status is one we trust for SOT.  A row marked
       ``provider_error`` may carry a number, but that number is not reliable.

    >>> has_usable_sot(0, DataQualityStatus.COMPLETE)
    True
    >>> has_usable_sot(None, DataQualityStatus.COMPLETE)
    False
    >>> has_usable_sot(3, DataQualityStatus.PROVIDER_ERROR)
    False
    """
    if shots_on_target is None:
        return False
    if data_quality_status is None:
        return True
    return data_quality_status in SOT_TRUSTWORTHY_STATUSES


def meets_threshold(shots_on_target: int | None, threshold: int) -> bool | None:
    """Did the player reach ``threshold`` shots on target?

    Returns ``None`` for an unknown value so callers must decide explicitly
    how to treat it, rather than silently receiving ``False``.

    >>> meets_threshold(2, 1)
    True
    >>> meets_threshold(0, 1)
    False
    >>> meets_threshold(None, 1) is None
    True
    """
    require_positive_integer(threshold, name="threshold")
    if shots_on_target is None:
        return None
    return shots_on_target >= threshold


def shot_accuracy(shots: int | None, shots_on_target: int | None) -> float | None:
    """Fraction of shots that were on target, or ``None`` when unknowable.

    A player who took zero shots has *undefined* accuracy, not 0%.

    >>> shot_accuracy(4, 2)
    0.5
    >>> shot_accuracy(0, 0) is None
    True
    >>> shot_accuracy(None, 2) is None
    True
    """
    if shots is None or shots_on_target is None or shots <= 0:
        return None
    return shots_on_target / shots
