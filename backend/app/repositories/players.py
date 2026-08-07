"""Database access for player search and match-history analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from app.analytics.models import MatchStatLine
from app.core.enums import SOT_TRUSTWORTHY_STATUSES, FixtureStatus, Venue
from app.core.text import normalize_name
from app.models import Competition, Fixture, Player, PlayerFixtureStats, Season, Team


@dataclass(frozen=True, slots=True)
class PlayerMatchQuery:
    """Provider-independent filter set accepted by player match queries."""

    starts_only: bool = True
    venue: Venue = Venue.ALL
    competition_id: int | None = None
    season: int | None = None
    last_n: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    minimum_minutes: int | None = None
    opponent_id: int | None = None
    team_id: int | None = None
    position: str | None = None
    minimum_sot: int | None = None


class PlayerRepository:
    """Player reads, including accent-folded paginated search."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, player_id: int) -> Player | None:
        statement = (
            select(Player).options(joinedload(Player.current_team)).where(Player.id == player_id)
        )
        return cast(Player | None, await self.session.scalar(statement))

    async def search(
        self,
        query: str | None,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Player], int]:
        """Search display names and return one deterministic page plus total."""
        normalized = normalize_name(query)
        conditions: list[ColumnElement[bool]] = []
        order_by: list[Any] = []

        if query is not None:
            if not normalized:
                return [], 0
            contains = f"%{normalized}%"
            conditions.append(
                or_(
                    Player.search_common_name.like(contains),
                    Player.search_name.like(contains),
                )
            )
            order_by.append(
                case(
                    (Player.search_common_name == normalized, 0),
                    (Player.search_name == normalized, 1),
                    (Player.search_common_name.startswith(normalized), 2),
                    (Player.search_name.startswith(normalized), 3),
                    else_=4,
                )
            )

        count_statement = select(func.count(Player.id))
        if conditions:
            count_statement = count_statement.where(*conditions)
        total = int(await self.session.scalar(count_statement) or 0)

        statement = select(Player).options(joinedload(Player.current_team))
        if conditions:
            statement = statement.where(*conditions)
        order_by.extend((Player.search_common_name, Player.id))
        statement = statement.order_by(*order_by).offset(offset).limit(limit)
        players = list((await self.session.scalars(statement)).unique().all())
        return players, total


class PlayerMatchRepository:
    """Filtered player match reads mapped into pure analytics inputs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _conditions(player_id: int, query: PlayerMatchQuery) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            PlayerFixtureStats.player_id == player_id,
            Competition.is_competitive.is_(True),
            Fixture.status == FixtureStatus.FINISHED,
        ]
        if query.starts_only:
            conditions.append(PlayerFixtureStats.started.is_(True))
        if query.venue is Venue.HOME:
            conditions.append(PlayerFixtureStats.home.is_(True))
        elif query.venue is Venue.AWAY:
            conditions.append(PlayerFixtureStats.home.is_(False))
        if query.competition_id is not None:
            conditions.append(Fixture.competition_id == query.competition_id)
        if query.season is not None:
            conditions.append(Season.season_year == query.season)
        if query.date_from is not None:
            conditions.append(
                Fixture.fixture_date >= datetime.combine(query.date_from, datetime.min.time(), UTC)
            )
        if query.date_to is not None:
            inclusive_end = datetime.combine(query.date_to, datetime.max.time(), UTC)
            conditions.append(Fixture.fixture_date <= inclusive_end)
        if query.minimum_minutes is not None:
            conditions.append(PlayerFixtureStats.minutes_played >= query.minimum_minutes)
        if query.opponent_id is not None:
            conditions.append(PlayerFixtureStats.opponent_id == query.opponent_id)
        if query.team_id is not None:
            conditions.append(PlayerFixtureStats.team_id == query.team_id)
        if query.position is not None:
            conditions.append(func.lower(PlayerFixtureStats.position) == query.position.casefold())
        if query.minimum_sot is not None:
            conditions.append(PlayerFixtureStats.shots_on_target >= query.minimum_sot)
            conditions.append(PlayerFixtureStats.data_quality_status.in_(SOT_TRUSTWORTHY_STATUSES))
        return conditions

    @staticmethod
    def _joins(statement: Any) -> Any:
        return (
            statement.join(Fixture, PlayerFixtureStats.fixture_id == Fixture.id)
            .join(Competition, Fixture.competition_id == Competition.id)
            .join(Season, Fixture.season_id == Season.id)
        )

    async def count(self, player_id: int, query: PlayerMatchQuery) -> int:
        statement = select(func.count(PlayerFixtureStats.id)).select_from(PlayerFixtureStats)
        statement = self._joins(statement).where(*self._conditions(player_id, query))
        count = int(await self.session.scalar(statement) or 0)
        return min(count, query.last_n) if query.last_n is not None else count

    async def list(
        self,
        player_id: int,
        query: PlayerMatchQuery,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[MatchStatLine]:
        team = aliased(Team, name="stats_team")
        opponent = aliased(Team, name="stats_opponent")
        statement = select(
            PlayerFixtureStats,
            Fixture.fixture_date,
            Fixture.competition_id,
            Fixture.season_id,
            Competition.name,
            Season.label,
            team.name,
            opponent.name,
        ).select_from(PlayerFixtureStats)
        statement = (
            self._joins(statement)
            .join(team, PlayerFixtureStats.team_id == team.id)
            .join(opponent, PlayerFixtureStats.opponent_id == opponent.id)
            .where(*self._conditions(player_id, query))
            .order_by(Fixture.fixture_date.desc(), Fixture.id.desc())
        )

        effective_limit = limit
        if query.last_n is not None:
            if offset >= query.last_n:
                return []
            remaining = query.last_n - offset
            effective_limit = (
                remaining if effective_limit is None else min(effective_limit, remaining)
            )
        if offset:
            statement = statement.offset(offset)
        if effective_limit is not None:
            statement = statement.limit(effective_limit)

        rows = (await self.session.execute(statement)).all()
        return [self._to_match_line(*row) for row in rows]

    @staticmethod
    def _to_match_line(
        stats: PlayerFixtureStats,
        fixture_date: datetime,
        competition_id: int,
        season_id: int,
        competition_name: str,
        season_label: str,
        team_name: str,
        opponent_name: str,
    ) -> MatchStatLine:
        # SQLite loses timezone metadata in tests; PostgreSQL returns aware UTC.
        # Re-attaching UTC is safe because fixture dates are stored in UTC.
        if fixture_date.utcoffset() is None:
            fixture_date = fixture_date.replace(tzinfo=UTC)
        else:
            fixture_date = fixture_date.astimezone(UTC)

        return MatchStatLine(
            fixture_id=stats.fixture_id,
            player_id=stats.player_id,
            team_id=stats.team_id,
            opponent_id=stats.opponent_id,
            fixture_date=fixture_date,
            competition_id=competition_id,
            season_id=season_id,
            home=stats.home,
            started=stats.started,
            substitute_appearance=stats.substitute_appearance,
            minutes_played=stats.minutes_played,
            position=stats.position,
            shots=stats.shots,
            shots_on_target=stats.shots_on_target,
            goals=stats.goals,
            assists=stats.assists,
            team_shots=stats.team_shots,
            team_shots_on_target=stats.team_shots_on_target,
            early_exit=stats.early_exit,
            data_quality_status=stats.data_quality_status,
            competition_name=competition_name,
            season_label=season_label,
            team_name=team_name,
            opponent_name=opponent_name,
        )
