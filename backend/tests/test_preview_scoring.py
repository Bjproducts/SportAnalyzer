"""Unit coverage for the explainable upcoming-fixture score."""

from app.analytics.models import RateResult
from app.analytics.preview import CandidatePreviewInput, score_candidate


def evidence(
    *,
    successes: int = 4,
    valid: int = 5,
    venue_successes: int = 2,
    venue_valid: int = 3,
    average_sot: float | None = 1.4,
    average_minutes: float | None = 82,
    pct_at_least_80: float | None = 0.8,
    allowed: float | None = 5.2,
    defense_matches: int = 5,
) -> CandidatePreviewInput:
    return CandidatePreviewInput(
        recent_rate=RateResult(successes, valid),
        venue_rate=RateResult(venue_successes, venue_valid, qualifier="home"),
        average_sot=average_sot,
        average_minutes=average_minutes,
        pct_at_least_80=pct_at_least_80,
        opponent_average_sot_allowed=allowed,
        opponent_defense_matches=defense_matches,
    )


def test_strong_evidence_scores_above_weak_evidence() -> None:
    strong = score_candidate(evidence())
    weak = score_candidate(
        evidence(
            successes=1,
            valid=5,
            venue_successes=0,
            average_sot=0.4,
            average_minutes=58,
            pct_at_least_80=0.0,
            allowed=2.8,
        )
    )

    assert strong.score > weak.score
    assert strong.confidence == "high"
    assert any("Opponent has allowed" in reason for reason in strong.reasons)
    assert any("Recent 1+ SOT rate" in risk for risk in weak.risks)
    assert any("Starting lineup" in risk for risk in strong.risks)


def test_small_sample_is_discounted_and_warned() -> None:
    full_sample = score_candidate(evidence(successes=5, valid=5))
    one_start = score_candidate(
        evidence(
            successes=1,
            valid=1,
            venue_successes=1,
            venue_valid=1,
            defense_matches=1,
        )
    )

    assert one_start.score < full_sample.score
    assert one_start.confidence == "low"
    assert any("Only 1 valid recent start" in risk for risk in one_start.risks)


def test_missing_evidence_stays_bounded_and_explicit() -> None:
    result = score_candidate(
        evidence(
            successes=0,
            valid=0,
            venue_successes=0,
            venue_valid=0,
            average_sot=None,
            average_minutes=None,
            pct_at_least_80=None,
            allowed=None,
            defense_matches=0,
        )
    )

    assert 0 <= result.score <= 100
    assert result.label == "speculative"
    assert result.confidence == "low"
    assert any("No valid recent starts" in risk for risk in result.risks)
    assert any("defensive SOT history" in risk for risk in result.risks)
