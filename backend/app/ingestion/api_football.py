"""Authorized API-Football adapter with rate limiting and retry handling."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

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
    "FT": FixtureStatus.FINISHED,
    "AET": FixtureStatus.FINISHED,
    "PEN": FixtureStatus.FINISHED,
    "NS": FixtureStatus.SCHEDULED,
    "TBD": FixtureStatus.SCHEDULED,
    "1H": FixtureStatus.LIVE,
    "2H": FixtureStatus.LIVE,
    "HT": FixtureStatus.LIVE,
    "PST": FixtureStatus.POSTPONED,
    "CANC": FixtureStatus.CANCELLED,
    "ABD": FixtureStatus.ABANDONED,
    "SUSP": FixtureStatus.SUSPENDED,
}


class ApiFootballProvider:
    name = "apifootball"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        calls_per_minute: int,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("FOOTBALL_API_KEY is required for the apifootball provider")
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={"x-apisports-key": api_key},
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._limiter = RateLimiter(calls_per_minute)
        self._max_retries = max_retries
        self._quota: ProviderQuota | None = None

    @property
    def quota(self) -> ProviderQuota | None:
        return self._quota

    async def _request(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        for attempt in range(self._max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(path, params=params)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(
                        "The football data provider could not be reached.",
                        provider=self.name,
                        retryable=True,
                    ) from exc
                await asyncio.sleep(2**attempt)
                continue

            self._quota = ProviderQuota(
                daily_limit=self._header_int(response, "x-ratelimit-requests-limit"),
                daily_remaining=self._header_int(response, "x-ratelimit-requests-remaining"),
                minute_limit=self._header_int(response, "x-ratelimit-limit"),
                minute_remaining=self._header_int(response, "x-ratelimit-remaining"),
            )

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                if attempt >= self._max_retries:
                    raise ProviderRateLimitError(
                        "The football data provider rate limit was exceeded.",
                        provider=self.name,
                        retry_after_seconds=retry_after,
                    )
                await asyncio.sleep(retry_after)
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                await asyncio.sleep(2**attempt)
                continue
            if response.is_error:
                raise ProviderError(
                    "The football data provider rejected the request.",
                    provider=self.name,
                    status_code=response.status_code,
                    retryable=False,
                )

            payload = response.json()
            errors = payload.get("errors") or {}
            if errors:
                raise ProviderError(
                    "The football data provider returned an application error.",
                    provider=self.name,
                    details={"errors": errors},
                )
            data = payload.get("response", [])
            return data if isinstance(data, list) else []
        return []

    async def search_players(self, query: str) -> list[ProviderPlayer]:
        rows = await self._request("/players/profiles", {"search": query})
        return [self._player(row.get("player", row)) for row in rows]

    async def get_fixtures(self, competition_id: int, season: int) -> list[ProviderFixture]:
        rows = await self._request("/fixtures", {"league": competition_id, "season": season})
        fixtures: list[ProviderFixture] = []
        for row in rows:
            league = row.get("league", {})
            fixture = row.get("fixture", {})
            teams = row.get("teams", {})
            goals = row.get("goals", {})
            fixtures.append(
                ProviderFixture(
                    id=int(fixture["id"]),
                    competition=ProviderCompetition(
                        int(league["id"]),
                        str(league.get("name") or "Unknown competition"),
                        league.get("country"),
                        league.get("logo"),
                    ),
                    season_year=int(league.get("season") or season),
                    season_label=str(league.get("season") or season),
                    fixture_date=datetime.fromisoformat(
                        str(fixture["date"]).replace("Z", "+00:00")
                    ),
                    home_team=self._team(teams.get("home", {})),
                    away_team=self._team(teams.get("away", {})),
                    status=_STATUS_MAP.get(
                        str(fixture.get("status", {}).get("short")), FixtureStatus.UNKNOWN
                    ),
                    home_score=goals.get("home"),
                    away_score=goals.get("away"),
                    venue=fixture.get("venue", {}).get("name"),
                    round=league.get("round"),
                    raw=row,
                )
            )
        return fixtures

    async def get_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        return await self._request("/fixtures/lineups", {"fixture": fixture_id})

    async def get_player_fixture_statistics(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> list[ProviderPlayerStat]:
        rows = await self._request("/fixtures/players", {"fixture": fixture_id})
        if home_team_id is None or away_team_id is None:
            fixture_rows = await self._request("/fixtures", {"id": fixture_id})
            fixture = fixture_rows[0] if fixture_rows else {}
            home_team_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_team_id = fixture.get("teams", {}).get("away", {}).get("id")
        if home_team_id is None or away_team_id is None:
            raise ProviderError(
                "The provider did not identify both fixture teams.",
                provider=self.name,
                retryable=False,
            )
        output: list[ProviderPlayerStat] = []
        for team_row in rows:
            team = team_row.get("team", {})
            team_id = int(team["id"])
            if team_id not in {home_team_id, away_team_id}:
                continue
            opponent_id = away_team_id if team_id == home_team_id else home_team_id
            for row in team_row.get("players", []):
                statistics = (row.get("statistics") or [{}])[0]
                games = statistics.get("games", {})
                shots = statistics.get("shots", {})
                sot = shots.get("on")
                quality = (
                    DataQualityStatus.COMPLETE if sot is not None else DataQualityStatus.MISSING_SOT
                )
                output.append(
                    ProviderPlayerStat(
                        player=self._player(row.get("player", {})),
                        team_id=team_id,
                        opponent_id=opponent_id,
                        home=team_id == home_team_id,
                        started=not bool(games.get("substitute")),
                        substitute_appearance=bool(games.get("substitute")),
                        minutes_played=games.get("minutes"),
                        position=games.get("position"),
                        shirt_number=games.get("number"),
                        shots=shots.get("total"),
                        shots_on_target=sot,
                        goals=statistics.get("goals", {}).get("total"),
                        assists=statistics.get("goals", {}).get("assists"),
                        key_passes=statistics.get("passes", {}).get("key"),
                        touches=statistics.get("touches"),
                        rating=self._float_or_none(games.get("rating")),
                        data_quality_status=quality,
                        raw=row,
                    )
                )
        return output

    @staticmethod
    def _team(row: dict[str, Any]) -> ProviderTeam:
        return ProviderTeam(
            id=int(row["id"]),
            name=str(row.get("name") or "Unknown team"),
            logo_url=row.get("logo"),
        )

    @staticmethod
    def _player(row: dict[str, Any]) -> ProviderPlayer:
        birth = row.get("birth", {}) or {}
        birth_date = date.fromisoformat(birth["date"]) if birth.get("date") else None
        return ProviderPlayer(
            id=int(row["id"]),
            full_name=str(row.get("firstname") or row.get("name") or "Unknown player")
            + (f" {row['lastname']}" if row.get("lastname") else ""),
            common_name=row.get("name"),
            date_of_birth=birth_date,
            nationality=row.get("nationality"),
            position=row.get("position"),
            photo_url=row.get("photo"),
        )

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if not isinstance(value, (str, int, float)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _header_int(response: httpx.Response, name: str) -> int | None:
        value = response.headers.get(name)
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
