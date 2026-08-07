"""Numeric primitives for the analytics engine.

The recurring theme: a calculation that cannot be performed returns ``None``.
Returning ``0.0`` for "no data" would state something the data does not
support, and that lie then propagates into every chart and ranking downstream.
"""

from __future__ import annotations

import math

#: z for a 95% confidence interval. Used by the Wilson score bound.
Z_95 = 1.959963984540054


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    """Divide, returning ``None`` instead of raising or fabricating a zero.

    >>> safe_divide(3, 4)
    0.75
    >>> safe_divide(0, 4)
    0.0
    >>> safe_divide(3, 0) is None
    True
    >>> safe_divide(None, 4) is None
    True
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def safe_rate(successes: int, trials: int) -> float | None:
    """Success rate in ``[0, 1]``, or ``None`` when there were no trials.

    Zero successes out of five is a real 0.0; zero out of zero is unknown.

    >>> safe_rate(0, 5)
    0.0
    >>> safe_rate(4, 5)
    0.8
    >>> safe_rate(0, 0) is None
    True
    """
    return safe_divide(successes, trials)


def per_90(total: float | None, minutes: float | None) -> float | None:
    """Scale a per-match total to a per-90-minutes figure.

    >>> per_90(4, 180)
    2.0
    >>> per_90(4, 0) is None
    True
    """
    if total is None or minutes is None or minutes <= 0:
        return None
    return total * 90.0 / minutes


def wilson_lower_bound(successes: int, trials: int, z: float = Z_95) -> float | None:
    """Lower bound of the Wilson score interval for a proportion.

    This is how the ranking layer refuses to let a tiny sample outrank a large
    one.  The bound answers "given this evidence, what rate can we be
    confident the player is *at least* achieving?", so a small sample is
    penalised by the arithmetic rather than by an arbitrary fudge factor:

    >>> round(wilson_lower_bound(2, 2), 3)     # a perfect 2 from 2
    0.342
    >>> round(wilson_lower_bound(18, 20), 3)   # 90% from a real sample
    0.699

    Returns ``None`` when there are no trials to reason about.
    """
    if trials <= 0:
        return None
    if successes < 0 or successes > trials:
        raise ValueError(f"successes ({successes}) must be within 0..trials ({trials}).")

    proportion = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    centre = proportion + z_squared / (2.0 * trials)
    margin = z * math.sqrt((proportion * (1.0 - proportion) + z_squared / (4.0 * trials)) / trials)
    return (centre - margin) / denominator


def mean(values: list[float] | list[int]) -> float | None:
    """Arithmetic mean, or ``None`` for an empty sequence.

    >>> mean([1, 2, 3])
    2.0
    >>> mean([]) is None
    True
    """
    if not values:
        return None
    return sum(values) / len(values)


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    """Round for presentation while preserving ``None``."""
    return None if value is None else round(value, digits)
