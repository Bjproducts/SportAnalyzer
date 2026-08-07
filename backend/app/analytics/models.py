"""Typed value objects for the analytics engine.

Everything here is a frozen dataclass.  The engine takes
:class:`MatchStatLine` inputs and returns these result objects - it never sees
an ORM instance, a database session or a provider payload.

The design rule that shapes every type in this module: **a percentage never
travels without the sample it came from**.  :class:`RateResult` carries the
success count, the valid denominator and the number of records excluded for
missing data, so no consumer can render "80%" without also being handed the
"8 of 10" that justifies it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import DataQualityStatus, PositionGroup


@dataclass(frozen=True, slots=True)
class MatchStatLine:
    """One player's record in one match - the engine's only input type.

    Deliberately flat and provider-agnostic.  ``shots_on_target`` is
    ``int | None`` and ``None`` always means *unreported*, never zero.
    """

    fixture_id: int
    player_id: int
    team_id: int
    opponent_id: int
    fixture_date: datetime
    competition_id: int
    season_id: int

    home: bool
    started: bool
    substitute_appearance: bool

    minutes_played: int | None = None
    position: str | None = None
    position_group: PositionGroup = PositionGroup.UNKNOWN

    shots: int | None = None
    shots_on_target: int | None = None
    goals: int | None = None
    assists: int | None = None

    team_shots: int | None = None
    team_shots_on_target: int | None = None

    early_exit: bool | None = None
    data_quality_status: DataQualityStatus = DataQualityStatus.COMPLETE

    # Display-only context, carried through so the API can render a row
    # without a second query.
    competition_name: str | None = None
    season_label: str | None = None
    team_name: str | None = None
    opponent_name: str | None = None

    def __post_init__(self) -> None:
        """Reject impossible inputs before they can corrupt an aggregate.

        The database enforces the same numeric and relationship constraints,
        but the analytics engine is intentionally database-independent and can
        be called with values from files, tests or provider normalisers.
        """
        identifiers = {
            "fixture_id": self.fixture_id,
            "player_id": self.player_id,
            "team_id": self.team_id,
            "opponent_id": self.opponent_id,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
        }
        for name, identifier in identifiers.items():
            if isinstance(identifier, bool) or identifier < 1:
                raise ValueError(f"{name} must be a positive integer.")

        if self.team_id == self.opponent_id:
            raise ValueError("team_id and opponent_id must differ.")
        if self.started and self.substitute_appearance:
            raise ValueError("An appearance cannot be both a start and a substitute appearance.")
        if self.fixture_date.utcoffset() is None:
            raise ValueError("fixture_date must be timezone-aware.")

        numeric_fields = {
            "minutes_played": self.minutes_played,
            "shots": self.shots,
            "shots_on_target": self.shots_on_target,
            "goals": self.goals,
            "assists": self.assists,
            "team_shots": self.team_shots,
            "team_shots_on_target": self.team_shots_on_target,
        }
        for name, numeric_value in numeric_fields.items():
            if numeric_value is not None and numeric_value < 0:
                raise ValueError(f"{name} cannot be negative.")

        if self.minutes_played is not None and self.minutes_played > 200:
            raise ValueError("minutes_played cannot exceed 200.")
        if (
            self.shots is not None
            and self.shots_on_target is not None
            and self.shots_on_target > self.shots
        ):
            raise ValueError("shots_on_target cannot exceed shots.")
        if (
            self.team_shots is not None
            and self.team_shots_on_target is not None
            and self.team_shots_on_target > self.team_shots
        ):
            raise ValueError("team_shots_on_target cannot exceed team_shots.")


@dataclass(frozen=True, slots=True)
class RateResult:
    """A success rate together with the evidence behind it.

    ``valid`` is the denominator actually used: records whose shots-on-target
    were unreported are counted in ``missing`` and excluded from ``valid``.
    """

    successes: int
    valid: int
    missing: int = 0
    #: What the denominator counts, used when describing the result in prose.
    noun: str = "starts"
    #: Optional qualifier, e.g. "away" -> "8 of 10 valid away starts".
    qualifier: str | None = None
    #: What counted as a success, e.g. "1+ SOT".
    criterion: str = "1+ SOT"

    def __post_init__(self) -> None:
        if self.successes < 0 or self.valid < 0 or self.missing < 0:
            raise ValueError("Rate counts cannot be negative.")
        if self.successes > self.valid:
            raise ValueError("successes cannot exceed valid records.")

    @property
    def percentage(self) -> float | None:
        """Rate in ``[0, 1]``, or ``None`` when there is nothing to divide by.

        Never returns ``0.0`` for an empty sample - see
        :func:`app.analytics.math.safe_rate`.
        """
        if self.valid <= 0:
            return None
        return self.successes / self.valid

    @property
    def failures(self) -> int:
        return max(self.valid - self.successes, 0)

    @property
    def total_considered(self) -> int:
        """Records looked at, including those excluded for missing data."""
        return self.valid + self.missing

    @property
    def has_sample(self) -> bool:
        return self.valid > 0

    def describe(self) -> str:
        """Human-readable summary that always states the sample size.

        >>> RateResult(8, 10, qualifier="away").describe()
        '8 of 10 valid away starts recorded 1+ SOT: 80.0%'
        >>> RateResult(8, 10, missing=2).describe()
        '8 of 10 valid starts recorded 1+ SOT: 80.0%, with 2 additional starts missing SOT data'
        >>> RateResult(0, 0).describe()
        'No valid starts with reported SOT data'
        """
        subject = f"{self.qualifier} {self.noun}" if self.qualifier else self.noun

        if self.valid <= 0:
            base = f"No valid {subject} with reported SOT data"
            if self.missing:
                return f"{base} ({self.missing} excluded for missing SOT data)"
            return base

        percentage = self.percentage
        assert percentage is not None  # guarded by the check above
        base = (
            f"{self.successes} of {self.valid} valid {subject} "
            f"recorded {self.criterion}: {percentage * 100:.1f}%"
        )
        if self.missing:
            plural = "start" if self.missing == 1 else "starts"
            if self.noun != "starts":
                plural = self.noun.rstrip("s") if self.missing == 1 else self.noun
            base += f", with {self.missing} additional {plural} missing SOT data"
        return base


@dataclass(frozen=True, slots=True)
class StreakSummary:
    """Consecutive-start streak information for a shots-on-target threshold.

    **Missing data is neutral.**  A start whose SOT was never reported neither
    extends nor breaks a streak: it is not evidence of success, and treating it
    as a failure would invent a result the provider never reported.  Such
    records are counted in ``missing_in_window`` so the UI can caveat the
    number rather than present it as clean.
    """

    threshold: int
    current: int
    longest: int
    #: Records skipped as neutral while walking the current streak.
    missing_in_window: int = 0
    #: Date of the most recent start that recorded fewer than ``threshold``.
    last_failure_date: datetime | None = None
    last_failure_fixture_id: int | None = None
    #: Starts since that failure, counting neutral records.
    starts_since_last_failure: int = 0
    #: True when the player has no recorded failure at all in the sample.
    never_failed: bool = False

    @property
    def is_reliable(self) -> bool:
        """False when missing data materially affects the current streak."""
        return self.missing_in_window == 0


@dataclass(frozen=True, slots=True)
class FormWindow:
    """A rate over the most recent N starts."""

    window: int
    rate: RateResult
    #: Starts actually available; smaller than ``window`` early in a career.
    starts_available: int


@dataclass(frozen=True, slots=True)
class SplitEntry:
    """One row of a categorical split (venue, competition, opponent...)."""

    key: str | int
    label: str
    rate: RateResult
    average_sot: float | None = None
    average_shots: float | None = None
    total_starts: int = 0


@dataclass(frozen=True, slots=True)
class VenueSplits:
    """Home / away / combined performance."""

    home: RateResult
    away: RateResult
    overall: RateResult


@dataclass(frozen=True, slots=True)
class MinutesProfile:
    """How much of a match the player typically completes."""

    starts_considered: int
    starts_with_known_minutes: int
    pct_at_least_60: float | None
    pct_at_least_80: float | None
    early_exits: int
    average_minutes_per_start: float | None
    total_minutes: int


@dataclass(frozen=True, slots=True)
class SotSummary:
    """The complete shots-on-target profile for one player over a filtered set.

    Every rate is a :class:`RateResult`, so the sample size travels with it.
    Every average is ``float | None``, never a fabricated zero.
    """

    player_id: int

    # --- Appearance counts ---------------------------------------------
    total_appearances: int
    total_starts: int
    substitute_appearances: int

    # --- Threshold hit rates (starts only) ------------------------------
    threshold_rates: dict[int, RateResult] = field(default_factory=dict)

    # --- Volume ----------------------------------------------------------
    total_shots: int = 0
    total_shots_on_target: int = 0
    #: Starts whose shots/SOT were unreported and so excluded from rates.
    starts_missing_sot: int = 0

    average_shots_per_start: float | None = None
    average_sot_per_start: float | None = None
    shots_per_90: float | None = None
    sot_per_90: float | None = None
    shot_accuracy: float | None = None

    # --- Team share -------------------------------------------------------
    team_sot_share: float | None = None

    # --- Minutes ----------------------------------------------------------
    minutes: MinutesProfile | None = None

    def rate_for(self, threshold: int) -> RateResult:
        """Rate for a threshold, or an empty result when it was not computed."""
        return self.threshold_rates.get(
            threshold,
            RateResult(successes=0, valid=0, missing=0, criterion=f"{threshold}+ SOT"),
        )

    @property
    def has_any_valid_start(self) -> bool:
        return any(rate.has_sample for rate in self.threshold_rates.values())
