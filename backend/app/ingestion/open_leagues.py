"""Requested leagues available in the official StatsBomb Open Data catalog."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class OpenDataLeague:
    slug: str
    competition_id: int
    season_id: int
    season_year: int
    season_label: str
    name: str
    country: str


# These are the newest freely available men's seasons for each requested
# league as of 2026-08-06. StatsBomb publishes a selected historical catalog,
# not a rolling/current feed. There is no Süper Lig season in Open Data.
OPEN_DATA_LEAGUES: tuple[OpenDataLeague, ...] = (
    OpenDataLeague("mls", 44, 107, 2023, "2023", "Major League Soccer", "USA"),
    OpenDataLeague("epl", 2, 27, 2015, "2015/2016", "Premier League", "England"),
    OpenDataLeague("la-liga", 11, 90, 2020, "2020/2021", "La Liga", "Spain"),
    OpenDataLeague("bundesliga", 9, 281, 2023, "2023/2024", "1. Bundesliga", "Germany"),
    OpenDataLeague("ligue-1", 7, 235, 2022, "2022/2023", "Ligue 1", "France"),
    OpenDataLeague("serie-a", 12, 27, 2015, "2015/2016", "Serie A", "Italy"),
)

UNAVAILABLE_REQUESTED_LEAGUES: tuple[str, ...] = ("super-lig",)

_BY_SLUG = {league.slug: league for league in OPEN_DATA_LEAGUES}
_ALIASES = {
    "major-league-soccer": "mls",
    "premier-league": "epl",
    "laliga": "la-liga",
    "german-league": "bundesliga",
    "france-league": "ligue-1",
    "french-league": "ligue-1",
    "ligue1": "ligue-1",
    "seriea": "serie-a",
}


def resolve_open_data_leagues(value: str) -> tuple[OpenDataLeague, ...]:
    requested = [part.strip().casefold() for part in value.split(",") if part.strip()]
    if not requested or "all" in requested:
        return OPEN_DATA_LEAGUES

    resolved: list[OpenDataLeague] = []
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
            "League is not available in StatsBomb Open Data.",
            details={
                "unavailable": unknown,
                "available": sorted(_BY_SLUG),
                "known_missing": list(UNAVAILABLE_REQUESTED_LEAGUES),
            },
        )
    return tuple(resolved)
