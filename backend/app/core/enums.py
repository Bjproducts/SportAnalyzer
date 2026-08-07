"""Enumerations shared by the ORM models, schemas and analytics engine.

All of these are persisted as VARCHAR + CHECK rather than native PostgreSQL
ENUM types.  Native enums require an ``ALTER TYPE`` migration to add a single
value and cannot drop one at all; VARCHAR + CHECK is a normal migration and
also works on SQLite, which the test suite uses.
"""

from __future__ import annotations

from enum import StrEnum


class CompetitionType(StrEnum):
    """Kind of competition, used to decide what counts as competitive."""

    LEAGUE = "league"
    DOMESTIC_CUP = "domestic_cup"
    LEAGUE_CUP = "league_cup"
    SUPER_CUP = "super_cup"
    INTERNATIONAL_CLUB = "international_club"
    INTERNATIONAL_NATIONAL = "international_national"
    FRIENDLY = "friendly"
    OTHER = "other"


#: Friendlies are excluded from analytics by default: team selection, effort
#: and substitution patterns make them non-comparable with competitive matches.
NON_COMPETITIVE_TYPES: frozenset[CompetitionType] = frozenset({CompetitionType.FRIENDLY})


class FixtureStatus(StrEnum):
    """Lifecycle state of a fixture."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


#: Only these statuses produce statistics that can be trusted as final.
COMPLETED_FIXTURE_STATUSES: frozenset[FixtureStatus] = frozenset({FixtureStatus.FINISHED})


class DataQualityStatus(StrEnum):
    """Per-record confidence in the ingested statistics.

    This drives both display and eligibility for rate calculations.
    ``MISSING_SOT`` in particular means "we do not know", which is emphatically
    not the same as "zero" - such rows are excluded from rate denominators.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING_SOT = "missing_sot"
    MISSING_LINEUP = "missing_lineup"
    PROVIDER_ERROR = "provider_error"
    MANUALLY_VERIFIED = "manually_verified"


#: Statuses whose shots-on-target value is trustworthy enough to count.
#: A row still needs a non-NULL ``shots_on_target`` to be included in a rate;
#: this set is the additional gate on top of that.
SOT_TRUSTWORTHY_STATUSES: frozenset[DataQualityStatus] = frozenset(
    {
        DataQualityStatus.COMPLETE,
        DataQualityStatus.MANUALLY_VERIFIED,
        # PARTIAL means some fields are absent; if SOT itself is present it is
        # still a real reported value, so it counts.
        DataQualityStatus.PARTIAL,
    }
)


class PreferredFoot(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"
    UNKNOWN = "unknown"


class PositionGroup(StrEnum):
    """Coarse positional grouping.

    The provider's per-match position string is stored verbatim alongside this;
    the group exists so filters and comparisons are stable across providers
    that spell positions differently.
    """

    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    ATTACKER = "attacker"
    UNKNOWN = "unknown"


class Venue(StrEnum):
    """Venue filter. Not a stored column - `player_fixture_stats.home` is a bool."""

    HOME = "home"
    AWAY = "away"
    ALL = "all"


class IngestionJobType(StrEnum):
    COMPETITIONS = "competitions"
    SEASONS = "seasons"
    TEAMS = "teams"
    FIXTURES = "fixtures"
    LINEUPS = "lineups"
    PLAYER_STATISTICS = "player_statistics"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    #: Completed, but some records failed. The failures are recorded, never
    #: silently dropped.
    PARTIAL = "partial"
    FAILED = "failed"


#: Length used for the VARCHAR backing every enum column above. Comfortably
#: longer than the longest value (`international_national`, 23 chars) so that
#: adding a value does not require a column widening migration.
ENUM_LENGTH = 40
