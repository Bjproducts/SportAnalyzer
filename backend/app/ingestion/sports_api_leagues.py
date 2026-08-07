"""Stable SportsAPI Pro V2 canonical IDs for tracked competitions."""

from app.ingestion.leagues import TrackedLeague

SPORTS_API_PRO_LEAGUES: tuple[TrackedLeague, ...] = (
    TrackedLeague("mls", 242, "Major League Soccer", "USA", calendar_year_season=True),
    TrackedLeague("epl", 17, "Premier League", "England"),
    TrackedLeague("la-liga", 8, "La Liga", "Spain"),
    TrackedLeague("bundesliga", 35, "Bundesliga", "Germany"),
    TrackedLeague("ligue-1", 34, "Ligue 1", "France"),
    TrackedLeague("serie-a", 23, "Serie A", "Italy"),
    TrackedLeague("super-lig", 52, "Süper Lig", "Türkiye"),
    TrackedLeague(
        "leagues-cup",
        13783,
        "Leagues Cup",
        "North & Central America",
        calendar_year_season=True,
    ),
)

_BY_SLUG = {league.slug: league for league in SPORTS_API_PRO_LEAGUES}

# Verified provider season IDs avoid a catalog request on repeat syncs and
# keep backfills working when the provider's season-list endpoint is empty.
SPORTS_API_PRO_SEASON_IDS: dict[tuple[int, int], int] = {
    (242, 2024): 57317,
    (242, 2025): 70158,
    (242, 2026): 86668,
    (17, 2024): 61627,
    (17, 2025): 76986,
    (17, 2026): 96668,
    (8, 2024): 61643,
    (8, 2025): 77559,
    (8, 2026): 97268,
    (35, 2024): 63516,
    (35, 2025): 77333,
    (35, 2026): 97464,
    (34, 2024): 61736,
    (34, 2025): 77356,
    (34, 2026): 96127,
    (23, 2024): 63515,
    (23, 2025): 76457,
    (23, 2026): 95836,
    (52, 2024): 63814,
    (52, 2025): 77805,
    (52, 2026): 98080,
}


def resolve_sports_api_leagues(value: str) -> tuple[TrackedLeague, ...]:
    from app.core.exceptions import ValidationError

    requested = [part.strip().casefold() for part in value.split(",") if part.strip()]
    if not requested or "all" in requested:
        return SPORTS_API_PRO_LEAGUES
    aliases = {
        "premier-league": "epl",
        "laliga": "la-liga",
        "ligue1": "ligue-1",
        "seriea": "serie-a",
        "superlig": "super-lig",
        "süper-lig": "super-lig",
        "turkish-league": "super-lig",
        "major-league-soccer": "mls",
        "north-america-tournament": "leagues-cup",
        "north-american-tournament": "leagues-cup",
        "leaguescup": "leagues-cup",
    }
    resolved: list[TrackedLeague] = []
    unknown: list[str] = []
    for value_part in requested:
        league = _BY_SLUG.get(aliases.get(value_part, value_part))
        if league is None:
            unknown.append(value_part)
        elif league not in resolved:
            resolved.append(league)
    if unknown:
        raise ValidationError(
            "Unknown SportsAPI Pro league selection.",
            details={"unknown": unknown, "allowed": sorted(_BY_SLUG)},
        )
    return tuple(resolved)
