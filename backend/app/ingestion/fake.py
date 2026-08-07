"""Deterministic provider used for development, tests and the product demo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.enums import DataQualityStatus, FixtureStatus
from app.ingestion.provider import (
    ProviderCompetition,
    ProviderFixture,
    ProviderPlayer,
    ProviderPlayerStat,
    ProviderTeam,
)


class FakeFootballProvider:
    name = "fake"

    def __init__(self) -> None:
        self.competition = ProviderCompetition(9001, "SOT Demo League", "England")
        self.teams = [
            ProviderTeam(42, "North London FC", "NLF", "England"),
            ProviderTeam(40, "Merseyside Reds", "MRD", "England"),
            ProviderTeam(49, "West London Blues", "WLB", "England"),
            ProviderTeam(50, "Manchester Sky", "MSK", "England"),
        ]
        self.players = [
            ProviderPlayer(
                101,
                "Bukayo Saka",
                "Bukayo Saka",
                nationality="England",
                position="RW",
                preferred_foot="left",
            ),
            ProviderPlayer(
                102,
                "Martin Ødegaard",
                "Martin Ødegaard",
                nationality="Norway",
                position="AM",
                preferred_foot="left",
            ),
            ProviderPlayer(
                103,
                "Kai Havertz",
                "Kai Havertz",
                nationality="Germany",
                position="CF",
                preferred_foot="left",
            ),
            ProviderPlayer(
                104,
                "Gabriel Martinelli",
                "Gabriel Martinelli",
                nationality="Brazil",
                position="LW",
                preferred_foot="right",
            ),
            ProviderPlayer(
                105,
                "Leandro Trossard",
                "Leandro Trossard",
                nationality="Belgium",
                position="LW",
                preferred_foot="both",
            ),
            ProviderPlayer(
                106,
                "Declan Rice",
                "Declan Rice",
                nationality="England",
                position="CM",
                preferred_foot="right",
            ),
        ]
        start = datetime(2025, 8, 16, 15, tzinfo=UTC)
        self.fixtures: list[ProviderFixture] = []
        for index in range(12):
            opponent = self.teams[1 + index % 3]
            home = index % 2 == 0
            self.fixtures.append(
                ProviderFixture(
                    id=7000 + index,
                    competition=self.competition,
                    season_year=2025,
                    season_label="2025/26",
                    fixture_date=start + timedelta(days=index * 7),
                    home_team=self.teams[0] if home else opponent,
                    away_team=opponent if home else self.teams[0],
                    status=FixtureStatus.FINISHED,
                    home_score=2 if home else index % 3,
                    away_score=index % 2 if home else 2,
                    venue="Demo Stadium",
                    round=f"Matchweek {index + 1}",
                    raw={"source": "deterministic-demo", "index": index},
                )
            )

    @property
    def quota(self) -> None:
        return None

    async def search_players(self, query: str) -> list[ProviderPlayer]:
        needle = query.casefold()
        return [player for player in self.players if needle in player.full_name.casefold()]

    async def get_fixtures(self, competition_id: int, season: int) -> list[ProviderFixture]:
        if competition_id != self.competition.id or season != 2025:
            return []
        return list(self.fixtures)

    async def get_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        return [{"fixture": fixture_id, "team": self.teams[0].id, "formation": "4-3-3"}]

    async def get_player_fixture_statistics(
        self,
        fixture_id: int,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> list[ProviderPlayerStat]:
        fixture = next((item for item in self.fixtures if item.id == fixture_id), None)
        if fixture is None:
            return []
        index = fixture.id - 7000
        home = fixture.home_team.id == self.teams[0].id
        opponent = fixture.away_team if home else fixture.home_team
        team_sot = 5 + index % 4
        stats: list[ProviderPlayerStat] = []
        for player_index, player in enumerate(self.players):
            sot = (index + player_index * 2) % 4
            shots = sot + 1 + (index + player_index) % 3
            quality = DataQualityStatus.COMPLETE
            if index == 4 and player_index == 3:
                sot = 0
                quality = DataQualityStatus.MISSING_SOT
            stats.append(
                ProviderPlayerStat(
                    player=player,
                    team_id=self.teams[0].id,
                    opponent_id=opponent.id,
                    home=home,
                    started=player_index < 5,
                    substitute_appearance=player_index == 5,
                    minutes_played=90 - player_index * 7 if player_index < 5 else 24,
                    position=player.position,
                    shirt_number=7 + player_index,
                    shots=shots,
                    shots_on_target=None if quality is DataQualityStatus.MISSING_SOT else sot,
                    goals=1 if sot >= 3 else 0,
                    assists=1 if (index + player_index) % 5 == 0 else 0,
                    key_passes=(index + player_index) % 4,
                    touches=45 + player_index * 6,
                    rating=6.5 + ((index + player_index) % 20) / 10,
                    team_shots=13 + index % 5,
                    team_shots_on_target=max(team_sot, sot),
                    data_quality_status=quality,
                    raw={"fixture": fixture_id, "player": player.id, "demo": True},
                )
            )
        return stats

    async def aclose(self) -> None:
        return None
