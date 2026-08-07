"""Keyless adapter for the official StatsBomb Open Data repository.

StatsBomb Open Data contains selected historical competitions rather than a
live, complete league feed.  Its event stream is nevertheless a strong fit
for this project because every shot has an explicit outcome, allowing a true
player-per-match shots-on-target value to be derived without scraping.
"""

from __future__ import annotations

import asyncio
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.enums import DataQualityStatus, FixtureStatus
from app.core.exceptions import ProviderError
from app.ingestion.provider import (
    ProviderCompetition,
    ProviderFixture,
    ProviderPlayer,
    ProviderPlayerStat,
    ProviderQuota,
    ProviderTeam,
)

DEFAULT_STATSBOMB_BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# A blocked attempt is not on target.  These are the StatsBomb outcomes where
# the ball would enter the goal without a goalkeeper intervention, plus goals.
_ON_TARGET_OUTCOMES = frozenset({"Goal", "Saved", "Saved to Post"})


class StatsBombOpenDataProvider:
    """Read selected historical match, lineup and event JSON without a key."""

    name = "statsbomb"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_STATSBOMB_BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "sot-analyzer/0.1 (StatsBomb Open Data client)"},
        )
        self._owns_client = client is None
        self._max_retries = max_retries
        self._lineup_cache: dict[int, list[dict[str, Any]]] = {}

    @property
    def quota(self) -> ProviderQuota | None:
        """The raw open-data repository does not expose a paid-plan quota."""
        return None

    async def _request(self, path: str) -> list[dict[str, Any]]:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise ProviderError(
                        "StatsBomb Open Data could not be reached.",
                        provider=self.name,
                        retryable=True,
                    ) from exc
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code >= 500 and attempt < self._max_retries:
                await asyncio.sleep(2**attempt)
                continue
            if response.is_error:
                raise ProviderError(
                    "StatsBomb Open Data rejected the request.",
                    provider=self.name,
                    status_code=response.status_code,
                    retryable=response.status_code >= 500,
                    details={"path": path},
                )
            payload = response.json()
            if not isinstance(payload, list):
                raise ProviderError(
                    "StatsBomb Open Data returned an unexpected payload.",
                    provider=self.name,
                    retryable=False,
                    details={"path": path},
                )
            return [row for row in payload if isinstance(row, dict)]
        return []

    async def search_players(self, query: str) -> list[ProviderPlayer]:
        # Open Data has no global player-search endpoint. Product search runs
        # against players already normalised into the local database.
        return []

    async def get_fixtures(self, competition_id: int, season: int) -> list[ProviderFixture]:
        """Return fixtures; ``season`` is StatsBomb's numeric season id."""
        rows = await self._request(f"matches/{competition_id}/{season}.json")
        fixtures: list[ProviderFixture] = []
        for row in rows:
            competition = row.get("competition") or {}
            season_row = row.get("season") or {}
            home_row = row.get("home_team") or {}
            away_row = row.get("away_team") or {}
            label = str(season_row.get("season_name") or season)
            fixtures.append(
                ProviderFixture(
                    id=int(row["match_id"]),
                    competition=ProviderCompetition(
                        id=int(competition.get("competition_id") or competition_id),
                        name=str(competition.get("competition_name") or "Unknown competition"),
                        country=competition.get("country_name"),
                    ),
                    season_year=self._season_year(label),
                    season_label=label,
                    fixture_date=self._fixture_datetime(row),
                    home_team=self._team(home_row, prefix="home"),
                    away_team=self._team(away_row, prefix="away"),
                    status=FixtureStatus.FINISHED,
                    home_score=self._optional_int(row.get("home_score")),
                    away_score=self._optional_int(row.get("away_score")),
                    venue=(row.get("stadium") or {}).get("name"),
                    round=(
                        f"Matchweek {row['match_week']}"
                        if row.get("match_week") is not None
                        else None
                    ),
                    raw=row,
                )
            )
        return fixtures

    async def get_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        cached = self._lineup_cache.get(fixture_id)
        if cached is not None:
            return cached
        rows = await self._request(f"lineups/{fixture_id}.json")
        self._lineup_cache[fixture_id] = rows
        return rows

    async def get_player_fixture_statistics(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> list[ProviderPlayerStat]:
        if home_team_id is None or away_team_id is None:
            raise ProviderError(
                "StatsBomb statistics require both fixture team identifiers.",
                provider=self.name,
                retryable=False,
            )

        lineups, events = await asyncio.gather(
            self.get_lineups(fixture_id),
            self._request(f"events/{fixture_id}.json"),
        )
        fixture_team_ids = {home_team_id, away_team_id}
        shots: Counter[int] = Counter()
        shots_on_target: Counter[int] = Counter()
        goals: Counter[int] = Counter()
        assists: Counter[int] = Counter()
        key_passes: Counter[int] = Counter()
        team_shots: Counter[int] = Counter()
        team_sot: Counter[int] = Counter()
        audit_events: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for event in events:
            player = event.get("player") or {}
            team = event.get("team") or {}
            player_id = self._optional_int(player.get("id"))
            team_id = self._optional_int(team.get("id"))
            if player_id is None or team_id not in fixture_team_ids:
                continue
            event_type = (event.get("type") or {}).get("name")
            if event_type == "Shot":
                shot = event.get("shot") or {}
                outcome = str((shot.get("outcome") or {}).get("name") or "")
                shots[player_id] += 1
                team_shots[team_id] += 1
                if outcome in _ON_TARGET_OUTCOMES:
                    shots_on_target[player_id] += 1
                    team_sot[team_id] += 1
                if outcome == "Goal":
                    goals[player_id] += 1
                audit_events[player_id].append(event)
            elif event_type == "Pass":
                pass_row = event.get("pass") or {}
                is_assist = pass_row.get("goal_assist") is True
                is_key_pass = pass_row.get("shot_assist") is True or is_assist
                if is_assist:
                    assists[player_id] += 1
                if is_key_pass:
                    key_passes[player_id] += 1
                if is_assist or is_key_pass:
                    audit_events[player_id].append(event)

        max_period = max((int(event.get("period") or 0) for event in events), default=2)
        regulation_minutes = 120 if max_period > 2 else 90
        output: list[ProviderPlayerStat] = []
        for team_row in lineups:
            team_id = self._optional_int(team_row.get("team_id"))
            if team_id not in fixture_team_ids:
                continue
            opponent_id = away_team_id if team_id == home_team_id else home_team_id
            for lineup_player in team_row.get("lineup") or []:
                positions = lineup_player.get("positions") or []
                if not positions:
                    continue  # unused substitute
                player_id = int(lineup_player["player_id"])
                started = any(
                    position.get("start_reason") == "Starting XI" or position.get("from") == "00:00"
                    for position in positions
                )
                position_name = str(positions[0].get("position") or "") or None
                player = ProviderPlayer(
                    id=player_id,
                    full_name=str(lineup_player.get("player_name") or "Unknown player"),
                    common_name=lineup_player.get("player_nickname"),
                    nationality=(lineup_player.get("country") or {}).get("name"),
                    position=self._broad_position(position_name),
                )
                output.append(
                    ProviderPlayerStat(
                        player=player,
                        team_id=team_id,
                        opponent_id=opponent_id,
                        home=team_id == home_team_id,
                        started=started,
                        substitute_appearance=not started,
                        minutes_played=self._minutes_played(positions, regulation_minutes),
                        position=position_name,
                        shirt_number=self._optional_int(lineup_player.get("jersey_number")),
                        shots=shots[player_id],
                        shots_on_target=shots_on_target[player_id],
                        goals=goals[player_id],
                        assists=assists[player_id],
                        key_passes=key_passes[player_id],
                        team_shots=team_shots[team_id],
                        team_shots_on_target=team_sot[team_id],
                        data_quality_status=DataQualityStatus.COMPLETE,
                        raw={
                            "lineup": lineup_player,
                            "relevant_events": audit_events[player_id],
                        },
                    )
                )
        return output

    @staticmethod
    def _team(row: dict[str, Any], *, prefix: str) -> ProviderTeam:
        country = row.get("country") or {}
        return ProviderTeam(
            id=int(row[f"{prefix}_team_id"]),
            name=str(row.get(f"{prefix}_team_name") or "Unknown team"),
            country=country.get("name"),
        )

    @staticmethod
    def _season_year(label: str) -> int:
        try:
            return int(label[:4])
        except ValueError as exc:
            raise ProviderError(
                "StatsBomb returned an invalid season label.",
                provider="statsbomb",
                details={"season_label": label},
            ) from exc

    @staticmethod
    def _fixture_datetime(row: dict[str, Any]) -> datetime:
        match_date = str(row["match_date"])
        kick_off = str(row.get("kick_off") or "00:00:00")
        value = datetime.fromisoformat(f"{match_date}T{kick_off}")
        # Open Data does not include a timezone offset. Preserve the published
        # clock and attach UTC so the database's timezone invariant still holds.
        return value.replace(tzinfo=UTC)

    @classmethod
    def _minutes_played(cls, positions: list[dict[str, Any]], match_minutes: int) -> int:
        match_end = match_minutes * 60
        intervals: list[tuple[int, int]] = []
        for position in positions:
            start = cls._clock_seconds(position.get("from"))
            end = cls._clock_seconds(position.get("to")) if position.get("to") else match_end
            start = min(max(start, 0), match_end)
            end = min(max(end, start), match_end)
            intervals.append((start, end))
        intervals.sort()
        merged: list[list[int]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        seconds = sum(end - start for start, end in merged)
        return min(200, math.ceil(seconds / 60))

    @staticmethod
    def _clock_seconds(value: object) -> int:
        parts = str(value or "0:0").split(":")
        try:
            return int(parts[0]) * 60 + int(float(parts[1]))
        except (IndexError, ValueError) as exc:
            raise ProviderError(
                "StatsBomb returned an invalid lineup clock.",
                provider="statsbomb",
                details={"clock": value},
            ) from exc

    @staticmethod
    def _broad_position(value: str | None) -> str | None:
        normalized = (value or "").casefold()
        if "goalkeeper" in normalized:
            return "Goalkeeper"
        if "back" in normalized:
            return "Defender"
        if "midfield" in normalized:
            return "Midfielder"
        if "forward" in normalized or "winger" in normalized:
            return "Attacker"
        return value

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
