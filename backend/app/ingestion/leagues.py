"""Stable API-Football identifiers for the product's supported leagues."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class TrackedLeague:
    slug: str
    provider_id: int
    name: str
    country: str
    calendar_year_season: bool = False


TRACKED_LEAGUES: tuple[TrackedLeague, ...] = (
    TrackedLeague("mls", 253, "Major League Soccer", "USA", calendar_year_season=True),
    TrackedLeague("epl", 39, "Premier League", "England"),
    TrackedLeague("la-liga", 140, "La Liga", "Spain"),
    TrackedLeague("bundesliga", 78, "Bundesliga", "Germany"),
    TrackedLeague("ligue-1", 61, "Ligue 1", "France"),
    TrackedLeague("serie-a", 135, "Serie A", "Italy"),
    TrackedLeague("super-lig", 203, "Süper Lig", "Türkiye"),
)

_BY_SLUG = {league.slug: league for league in TRACKED_LEAGUES}
_ALIASES = {
    "all": "all",
    "major-league-soccer": "mls",
    "premier-league": "epl",
    "english-premier-league": "epl",
    "laliga": "la-liga",
    "spanish-league": "la-liga",
    "german-league": "bundesliga",
    "france-league": "ligue-1",
    "french-league": "ligue-1",
    "ligue1": "ligue-1",
    "seriea": "serie-a",
    "turkish-league": "super-lig",
    "superlig": "super-lig",
    "süper-lig": "super-lig",
}


def resolve_leagues(value: str) -> tuple[TrackedLeague, ...]:
    """Resolve a comma-separated set of canonical slugs or friendly aliases."""
    requested = [part.strip().casefold() for part in value.split(",") if part.strip()]
    if not requested or "all" in requested:
        return TRACKED_LEAGUES

    resolved: list[TrackedLeague] = []
    unknown: list[str] = []
    for raw_slug in requested:
        slug = _ALIASES.get(raw_slug, raw_slug)
        league = _BY_SLUG.get(slug)
        if league is None:
            unknown.append(raw_slug)
        elif league not in resolved:
            resolved.append(league)
    if unknown:
        raise ValidationError(
            "Unknown league selection.",
            details={"unknown": unknown, "allowed": sorted(_BY_SLUG)},
        )
    return tuple(resolved)
