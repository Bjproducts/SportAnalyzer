"""Authorized SportsAPI Pro V2 adapter.

The provider omits many zero-valued player fields from JSON.  In particular,
``onTargetScoringAttempt`` is absent when it is zero, while ``totalShots`` is
present.  We only coerce an absent SOT field to zero when ``totalShots`` is
reported; otherwise SOT remains unknown, preserving the application's central
missing-is-not-zero invariant.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from app.core.enums import DataQualityStatus, FixtureStatus
from app.core.exceptions import ProviderError, ProviderRateLimitError
from app.ingestion.provider import (
    ProviderCompetition,
    ProviderFixture,
    ProviderPlayer,
    ProviderPlayerStat,
    ProviderQuota,
    ProviderTeam,
)
from app.ingestion.rate_limit import RateLimiter

_STATUS_MAP = {
    0: FixtureStatus.SCHEDULED,
    6: FixtureStatus.LIVE,
    7: FixtureStatus.LIVE,
    31: FixtureStatus.LIVE,
    40: FixtureStatus.LIVE,
    41: FixtureStatus.LIVE,
    50: FixtureStatus.LIVE,
    60: FixtureStatus.POSTPONED,
    70: FixtureStatus.CANCELLED,
    80: FixtureStatus.SUSPENDED,
    90: FixtureStatus.ABANDONED,
    100: FixtureStatus.FINISHED,
    110: FixtureStatus.FINISHED,
    120: FixtureStatus.FINISHED,
}


class SportsApiProProvider:
    """SportsAPI Pro client with season resolution and quota-safe pagination."""

    name = "sportsapipro"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        calls_per_minute: int,
        timeout_seconds: float,
        max_retries: int,
        history_pages: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("SPORTS_API_PRO_KEY is required for the sportsapipro provider")
        if not 1 <= history_pages <= 100:
            raise ValueError("SPORTS_API_PRO_HISTORY_PAGES must be between 1 and 100")
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={"x-api-key": api_key},
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._limiter = RateLimiter(calls_per_minute)
        self._max_retries = max_retries
        self._history_pages = history_pages
        self._quota: ProviderQuota | None = None
        self._season_cache: dict[tuple[int, int], dict[str, Any]] = {}

    @property
    def quota(self) -> ProviderQuota | None:
        return self._quota

    def remember_season(self, competition_id: int, year: int, season_id: int) -> None:
        """Prime a previously verified season ID and skip a catalog API call."""
        if competition_id <= 0 or season_id <= 0 or not 1850 <= year <= 2200:
            raise ValueError("competition, year and season IDs must be valid positive values")
        self._season_cache[(competition_id, year)] = {
            "id": season_id,
            "name": str(year),
            "year": str(year),
        }

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(path.lstrip("/"), params=params)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(
                        "SportsAPI Pro could not be reached.",
                        provider=self.name,
                        retryable=True,
                    ) from exc
                await asyncio.sleep(2**attempt)
                continue

            daily_limit = self._header_int(response, "X-RateLimit-Limit")
            daily_remaining = self._header_int(response, "X-RateLimit-Remaining")
            if daily_limit is not None or daily_remaining is not None:
                self._quota = ProviderQuota(
                    daily_limit=daily_limit,
                    daily_remaining=daily_remaining,
                )
            if response.status_code == 429:
                retry_after = self._retry_after(response)
                if attempt >= self._max_retries:
                    raise ProviderRateLimitError(
                        "SportsAPI Pro's daily or burst limit was exceeded.",
                        provider=self.name,
                        retry_after_seconds=retry_after,
                    )
                await asyncio.sleep(min(retry_after or 60.0, 60.0))
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                await asyncio.sleep(2**attempt)
                continue
            if response.is_error:
                raise ProviderError(
                    "SportsAPI Pro rejected the request.",
                    provider=self.name,
                    status_code=response.status_code,
                    retryable=response.status_code >= 500,
                    details={"path": path},
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderError(
                    "SportsAPI Pro returned an unexpected payload.",
                    provider=self.name,
                    details={"path": path},
                )
            if payload.get("success") is False:
                error = payload.get("error") or {}
                raise ProviderError(
                    str(error.get("message") or "SportsAPI Pro returned an application error."),
                    provider=self.name,
                    retryable=False,
                    details={"code": error.get("code"), "path": path},
                )
            return payload
        return {}

    async def search_players(self, query: str) -> list[ProviderPlayer]:
        payload = await self._request("api/search", {"q": query})
        results = (payload.get("data") or {}).get("results") or []
        players: list[ProviderPlayer] = []
        for result in results:
            if result.get("type") != "player":
                continue
            entity = result.get("entity") or {}
            if entity.get("id") is not None:
                players.append(self._player(entity))
        return players

    async def get_fixtures(self, competition_id: int, season: int) -> list[ProviderFixture]:
        season_row = await self._resolve_season(competition_id, season)
        season_id = int(season_row["id"])
        rows: list[dict[str, Any]] = []
        for page in range(self._history_pages):
            try:
                payload = await self._request(
                    f"api/tournament/{competition_id}/season/{season_id}/events/last/{page}"
                )
            except ProviderError as exc:
                # A new season with no completed matches also uses 404 for an
                # empty history page.
                if exc.status_code == 404:
                    break
                raise
            page_rows = self._events(payload)
            rows.extend(page_rows)
            if len(page_rows) < 30:
                break
        try:
            next_payload = await self._request(
                f"api/tournament/{competition_id}/season/{season_id}/events/next/0"
            )
        except ProviderError as exc:
            # Completed historical seasons legitimately have no "next" page;
            # this provider represents that normal empty state as HTTP 404.
            if exc.status_code != 404:
                raise
        else:
            rows.extend(self._events(next_payload))

        unique: dict[int, ProviderFixture] = {}
        for row in rows:
            fixture = self._fixture(row, requested_season=season)
            unique[fixture.id] = fixture
        return list(unique.values())

    async def get_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        payload = await self._request(f"api/match/{fixture_id}/lineups")
        data = payload.get("data") or {}
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    async def get_player_fixture_statistics(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> list[ProviderPlayerStat]:
        if home_team_id is None or away_team_id is None:
            raise ProviderError(
                "SportsAPI Pro statistics require both fixture team identifiers.",
                provider=self.name,
                retryable=False,
            )
        payload = await self._request(f"api/match/{fixture_id}/player-statistics")
        data = payload.get("data") or {}
        sides = (
            ("home", home_team_id, away_team_id),
            ("away", away_team_id, home_team_id),
        )
        normalized: list[tuple[str, int, int, dict[str, Any]]] = []
        for side, team_id, opponent_id in sides:
            side_rows = data.get(side) or [] if isinstance(data, dict) else []
            for row in side_rows:
                if not isinstance(row, dict) or not self._appeared(row):
                    continue
                normalized.append((side, team_id, opponent_id, row))

        team_totals: dict[int, tuple[int | None, int | None]] = {}
        for _, team_id, _, _ in normalized:
            team_rows = [row for _, row_team, _, row in normalized if row_team == team_id]
            shots_values = [
                self._optional_int((row.get("statistics") or {}).get("totalShots"))
                for row in team_rows
            ]
            sot_values = [self._player_sot(row.get("statistics") or {}) for row in team_rows]
            team_totals[team_id] = (
                sum(value for value in shots_values if value is not None)
                if any(value is not None for value in shots_values)
                else None,
                sum(value for value in sot_values if value is not None)
                if any(value is not None for value in sot_values)
                else None,
            )

        output: list[ProviderPlayerStat] = []
        for side, team_id, opponent_id, row in normalized:
            stats = row.get("statistics") or {}
            player_row = row.get("player") or {}
            shots = self._optional_int(stats.get("totalShots"))
            sot = self._player_sot(stats)
            quality = (
                DataQualityStatus.COMPLETE if sot is not None else DataQualityStatus.MISSING_SOT
            )
            team_shots, team_sot = team_totals[team_id]
            substitute = bool(row.get("substitute"))
            output.append(
                ProviderPlayerStat(
                    player=self._player(player_row),
                    team_id=team_id,
                    opponent_id=opponent_id,
                    home=side == "home",
                    started=not substitute,
                    substitute_appearance=substitute,
                    minutes_played=self._optional_int(stats.get("minutesPlayed")),
                    position=row.get("position") or player_row.get("position"),
                    shirt_number=self._optional_int(
                        row.get("shirtNumber") or row.get("jerseyNumber")
                    ),
                    shots=shots,
                    shots_on_target=sot,
                    goals=self._zero_when_covered(stats, "goals"),
                    assists=self._zero_when_covered(stats, "goalAssist"),
                    key_passes=self._optional_int(stats.get("keyPass")),
                    touches=self._optional_int(stats.get("touches")),
                    rating=self._float_or_none(stats.get("rating")),
                    team_shots=team_shots,
                    team_shots_on_target=team_sot,
                    data_quality_status=quality,
                    raw=row,
                )
            )
        return output

    async def _resolve_season(self, competition_id: int, year: int) -> dict[str, Any]:
        cache_key = (competition_id, year)
        cached = self._season_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = await self._request(f"api/tournaments/{competition_id}/seasons")
        raw_seasons: object = (
            payload.get("seasons") or ((payload.get("data") or {}).get("seasons")) or []
        )
        seasons = (
            [cast(dict[str, Any], row) for row in raw_seasons if isinstance(row, dict)]
            if isinstance(raw_seasons, list)
            else []
        )
        split_prefix = f"{year % 100:02d}/"
        for row in seasons:
            label = str(row.get("year") or row.get("name") or "")
            if label == str(year) or label.startswith(split_prefix):
                self._season_cache[cache_key] = row
                return row
        raise ProviderError(
            "SportsAPI Pro has no matching season for the requested year.",
            provider=self.name,
            retryable=False,
            details={
                "competition_id": competition_id,
                "year": year,
                "available": [str(row.get("year") or row.get("name")) for row in seasons[:8]],
            },
        )

    def _fixture(self, row: dict[str, Any], *, requested_season: int) -> ProviderFixture:
        tournament = row.get("tournament") or {}
        canonical = tournament.get("uniqueTournament") or tournament
        category = canonical.get("category") or tournament.get("category") or {}
        home = row.get("homeTeam") or {}
        away = row.get("awayTeam") or {}
        season = row.get("season") or {}
        label = str(season.get("name") or season.get("year") or requested_season)
        status = row.get("status") or {}
        venue = row.get("venue") or {}
        round_info = row.get("roundInfo") or {}
        competition_id = self._optional_int(canonical.get("id") or tournament.get("id"))
        if competition_id is None:
            raise ProviderError(
                "SportsAPI Pro fixture has no competition identifier.",
                provider=self.name,
                retryable=False,
                details={"fixture_id": row.get("id")},
            )
        status_code = self._optional_int(status.get("code"))
        return ProviderFixture(
            id=int(row["id"]),
            competition=ProviderCompetition(
                id=competition_id,
                name=str(canonical.get("name") or tournament.get("name") or "Unknown competition"),
                country=category.get("name"),
            ),
            season_year=requested_season,
            season_label=label,
            fixture_date=datetime.fromtimestamp(int(row["startTimestamp"]), tz=UTC),
            home_team=self._team(home),
            away_team=self._team(away),
            status=_STATUS_MAP.get(
                status_code if status_code is not None else -1,
                FixtureStatus.UNKNOWN,
            ),
            home_score=self._score(row.get("homeScore")),
            away_score=self._score(row.get("awayScore")),
            venue=venue.get("name"),
            round=(
                f"Matchweek {round_info['round']}" if round_info.get("round") is not None else None
            ),
            raw=row,
        )

    @staticmethod
    def _events(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, dict):
            rows = data.get("events") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = payload.get("events") or []
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _team(row: dict[str, Any]) -> ProviderTeam:
        country = row.get("country") or {}
        return ProviderTeam(
            id=int(row["id"]),
            name=str(row.get("name") or "Unknown team"),
            short_name=row.get("shortName") or row.get("nameCode"),
            country=country.get("name"),
        )

    @classmethod
    def _player(cls, row: dict[str, Any]) -> ProviderPlayer:
        timestamp = cls._optional_int(row.get("dateOfBirthTimestamp"))
        birth = datetime.fromtimestamp(timestamp, tz=UTC).date() if timestamp is not None else None
        country = row.get("country") or {}
        return ProviderPlayer(
            id=int(row["id"]),
            full_name=str(row.get("name") or row.get("shortName") or "Unknown player"),
            common_name=row.get("shortName"),
            date_of_birth=birth,
            nationality=country.get("name"),
            position=row.get("position"),
        )

    @staticmethod
    def _appeared(row: dict[str, Any]) -> bool:
        stats = row.get("statistics") or {}
        if not row.get("substitute"):
            return True
        return stats.get("minutesPlayed") is not None

    @classmethod
    def _player_sot(cls, stats: dict[str, Any]) -> int | None:
        explicit = cls._optional_int(stats.get("onTargetScoringAttempt"))
        if explicit is not None:
            return explicit
        return 0 if cls._optional_int(stats.get("totalShots")) is not None else None

    @classmethod
    def _zero_when_covered(cls, stats: dict[str, Any], field: str) -> int | None:
        explicit = cls._optional_int(stats.get(field))
        if explicit is not None:
            return explicit
        return 0 if cls._optional_int(stats.get("totalShots")) is not None else None

    @classmethod
    def _score(cls, value: object) -> int | None:
        if isinstance(value, dict):
            return cls._optional_int(value.get("current"))
        return cls._optional_int(value)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _header_int(response: httpx.Response, name: str) -> int | None:
        try:
            value = response.headers.get(name)
            return int(value) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            value = response.headers.get("Retry-After")
            return float(value) if value is not None else None
        except ValueError:
            return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
