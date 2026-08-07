"""Pure, explainable scoring for an upcoming shots-on-target matchup.

The result is a research score, not a probability.  Keeping this module free
of ORM and provider objects makes every weight and warning independently
testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.math import wilson_lower_bound
from app.analytics.models import RateResult


@dataclass(frozen=True, slots=True)
class CandidatePreviewInput:
    """Evidence available before an upcoming fixture."""

    recent_rate: RateResult
    venue_rate: RateResult
    average_sot: float | None
    average_minutes: float | None
    pct_at_least_80: float | None
    opponent_average_sot_allowed: float | None
    opponent_defense_matches: int


@dataclass(frozen=True, slots=True)
class CandidatePreviewScore:
    """A bounded score plus the evidence language used by the product."""

    score: int
    label: str
    confidence: str
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(value, high))


def score_candidate(evidence: CandidatePreviewInput) -> CandidatePreviewScore:
    """Score one player without pretending the result is a probability.

    Weights total 100 points before the sample-confidence discount:

    * recent 1+ SOT rate: 35
    * Wilson sample-adjusted rate: 20
    * average SOT volume: 15
    * same-venue hit rate: 10
    * minutes/role stability: 10
    * opponent SOT allowed: 10
    """

    recent = evidence.recent_rate.percentage or 0.0
    adjusted = (
        wilson_lower_bound(
            evidence.recent_rate.successes,
            evidence.recent_rate.valid,
        )
        or 0.0
    )
    volume = _clamp((evidence.average_sot or 0.0) / 2.0)
    venue = evidence.venue_rate.percentage
    venue_component = recent if venue is None else venue

    if evidence.pct_at_least_80 is not None:
        minutes_component = evidence.pct_at_least_80
    elif evidence.average_minutes is not None:
        minutes_component = _clamp((evidence.average_minutes - 45.0) / 45.0)
    else:
        minutes_component = 0.4

    allowed = evidence.opponent_average_sot_allowed
    defense_component = 0.5 if allowed is None else _clamp((allowed - 2.0) / 5.0)

    raw_score = (
        recent * 35.0
        + adjusted * 20.0
        + volume * 15.0
        + venue_component * 10.0
        + minutes_component * 10.0
        + defense_component * 10.0
    )
    sample_confidence = _clamp(evidence.recent_rate.valid / 5.0)
    score = round(raw_score * (0.7 + 0.3 * sample_confidence))

    if evidence.recent_rate.valid >= 5 and evidence.opponent_defense_matches >= 5:
        confidence = "high"
    elif evidence.recent_rate.valid >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    if score >= 70:
        label = "strong"
    elif score >= 50:
        label = "viable"
    else:
        label = "speculative"

    reasons: list[str] = []
    risks: list[str] = ["Starting lineup and role are not confirmed."]

    if evidence.recent_rate.valid:
        reasons.append(
            f"Recorded 1+ SOT in {evidence.recent_rate.successes} of "
            f"{evidence.recent_rate.valid} recent starts."
        )
    if evidence.average_sot is not None and evidence.average_sot >= 1.2:
        reasons.append(f"Averages {evidence.average_sot:.2f} SOT per recent start.")
    if venue is not None and evidence.venue_rate.valid >= 2 and venue >= recent + 0.1:
        reasons.append(
            f"Venue record improves to {venue * 100:.0f}% "
            f"({evidence.venue_rate.successes}/{evidence.venue_rate.valid})."
        )
    if allowed is not None and allowed >= 5.0:
        reasons.append(f"Opponent has allowed {allowed:.1f} SOT per recent match.")
    if evidence.average_minutes is not None and evidence.average_minutes >= 75:
        reasons.append(f"Averages {evidence.average_minutes:.0f} minutes when starting.")

    if evidence.recent_rate.valid == 0:
        risks.append("No valid recent starts with reported SOT data.")
    elif evidence.recent_rate.valid < 3:
        risks.append(
            f"Only {evidence.recent_rate.valid} valid recent "
            f"{'start' if evidence.recent_rate.valid == 1 else 'starts'} available."
        )
    elif recent <= 0.4:
        risks.append(f"Recent 1+ SOT rate is only {recent * 100:.0f}%.")

    if venue is None:
        risks.append("No matching home/away starts in the recent window.")
    elif evidence.venue_rate.valid >= 2 and venue + 0.1 < recent:
        risks.append(
            f"Matching venue rate falls to {venue * 100:.0f}% "
            f"({evidence.venue_rate.successes}/{evidence.venue_rate.valid})."
        )
    if evidence.average_minutes is None:
        risks.append("Recent starting-minute data is unavailable.")
    elif evidence.average_minutes < 65:
        risks.append(f"Averages only {evidence.average_minutes:.0f} minutes when starting.")
    if allowed is None:
        risks.append("Opponent defensive SOT history is unavailable.")
    elif allowed <= 3.5:
        risks.append(f"Opponent has allowed only {allowed:.1f} SOT per recent match.")
    if evidence.recent_rate.missing:
        risks.append(
            f"{evidence.recent_rate.missing} recent "
            f"{'start is' if evidence.recent_rate.missing == 1 else 'starts are'} missing SOT data."
        )

    if not reasons:
        reasons.append("Candidate is included from the current squad; evidence is limited.")

    return CandidatePreviewScore(
        score=max(0, min(score, 100)),
        label=label,
        confidence=confidence,
        reasons=tuple(reasons[:4]),
        risks=tuple(risks[:5]),
    )
