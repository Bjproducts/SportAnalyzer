"""Team squad, ranking and multi-player comparison orchestration."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.analytics import (
    build_sot_summary,
    compute_form_window,
    compute_streaks,
    compute_venue_splits,
    wilson_lower_bound,
)
from app.core.enums import Venue
from app.core.exceptions import NotFoundError, ValidationError
from app.core.text import normalize_name
from app.models import Player, Team
from app.repositories.players import PlayerMatchQuery, PlayerMatchRepository, PlayerRepository
from app.schemas.players import PaginationMeta, RateResponse, player_list_item
from app.schemas.teams import (
    PlayerComparisonEntry,
    PlayerComparisonResponse,
    RankingEntry,
    TeamPlayersResponse,
    TeamRankingsResponse,
    TeamResponse,
    TeamsResponse,
)


class TeamAnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.matches = PlayerMatchRepository(session)
        self.players = PlayerRepository(session)

    async def _require_team(self, team_id: int) -> Team:
        team = await self.session.get(Team, team_id)
        if team is None:
            raise NotFoundError("Team", team_id)
        return team

    async def list_teams(self, query: str | None, *, page: int, page_size: int) -> TeamsResponse:
        statement = select(Team)
        count_statement = select(func.count(Team.id))
        squad_size = (
            select(func.count(Player.id))
            .where(Player.current_team_id == Team.id)
            .correlate(Team)
            .scalar_subquery()
        )
        normalized = normalize_name(query)
        if query is not None:
            pattern = f"%{normalized}%"
            condition = or_(Team.search_name.like(pattern), Team.name.ilike(pattern))
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        total = int(await self.session.scalar(count_statement) or 0)
        teams = list(
            (
                await self.session.scalars(
                    statement.order_by(squad_size.desc(), Team.search_name, Team.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return TeamsResponse(
            items=[TeamResponse.model_validate(team) for team in teams],
            pagination=PaginationMeta.build(page=page, page_size=page_size, total=total),
        )

    async def get_team(self, team_id: int) -> TeamResponse:
        return TeamResponse.model_validate(await self._require_team(team_id))

    async def get_players(self, team_id: int) -> TeamPlayersResponse:
        team = await self._require_team(team_id)
        statement = (
            select(Player)
            .options(joinedload(Player.current_team))
            .where(Player.current_team_id == team_id)
            .order_by(Player.search_common_name, Player.id)
        )
        players = list((await self.session.scalars(statement)).unique().all())
        return TeamPlayersResponse(
            team=TeamResponse.model_validate(team),
            items=[player_list_item(player) for player in players],
        )

    async def rankings(
        self,
        team_id: int,
        *,
        venue: Venue,
        competition_id: int | None,
        season: int | None,
        minimum_starts: int,
        threshold: int,
        last_n: int,
        limit: int,
    ) -> TeamRankingsResponse:
        squad = await self.get_players(team_id)
        entries: list[tuple[RankingEntry, tuple[float, ...]]] = []
        for player_view in squad.items:
            lines = await self.matches.list(
                player_view.id,
                PlayerMatchQuery(
                    starts_only=True,
                    venue=venue,
                    competition_id=competition_id,
                    season=season,
                    team_id=team_id,
                    last_n=last_n,
                ),
            )
            summary = build_sot_summary(lines, player_id=player_view.id)
            rate = summary.rate_for(threshold)
            recent = compute_form_window(lines, 5, threshold).rate
            streak = compute_streaks(lines, threshold)
            adjusted = wilson_lower_bound(rate.successes, rate.valid)
            average_minutes = summary.minutes.average_minutes_per_start if summary.minutes else None
            eligible = rate.valid >= minimum_starts
            entry = RankingEntry(
                rank=0,
                eligible=eligible,
                player=player_view,
                rate=RateResponse.from_result(rate),
                last_five_rate=recent.percentage,
                average_sot=summary.average_sot_per_start,
                average_minutes=average_minutes,
                current_streak=streak.current,
                sample_adjusted_rate=adjusted,
            )
            sort_key = (
                float(eligible),
                adjusted if adjusted is not None else -1.0,
                rate.percentage if rate.percentage is not None else -1.0,
                float(rate.valid),
                recent.percentage if recent.percentage is not None else -1.0,
                summary.average_sot_per_start or -1.0,
                average_minutes or -1.0,
            )
            entries.append((entry, sort_key))
        entries.sort(key=lambda item: item[1], reverse=True)
        ranked = [
            entry.model_copy(update={"rank": index}) for index, (entry, _) in enumerate(entries, 1)
        ][:limit]
        return TeamRankingsResponse(
            team=squad.team,
            venue=venue,
            threshold=threshold,
            minimum_starts=minimum_starts,
            last_n=last_n,
            limit=limit,
            items=ranked,
        )

    async def compare_players(
        self, player_ids: list[int], query: PlayerMatchQuery
    ) -> PlayerComparisonResponse:
        if len(set(player_ids)) != len(player_ids):
            raise ValidationError("player_ids must not contain duplicates.")
        items: list[PlayerComparisonEntry] = []
        for player_id in player_ids:
            player = await self.players.get(player_id)
            if player is None:
                raise NotFoundError("Player", player_id)
            lines = await self.matches.list(player_id, query)
            summary = build_sot_summary(lines, player_id=player_id)
            venues = compute_venue_splits(lines)
            last_five = compute_form_window(lines, 5).rate
            last_ten = compute_form_window(lines, 10).rate
            items.append(
                PlayerComparisonEntry(
                    player=player_list_item(player),
                    one_plus_rate=RateResponse.from_result(summary.rate_for(1)),
                    two_plus_rate=RateResponse.from_result(summary.rate_for(2)),
                    average_sot=summary.average_sot_per_start,
                    sot_per_90=summary.sot_per_90,
                    home_rate=RateResponse.from_result(venues.home),
                    away_rate=RateResponse.from_result(venues.away),
                    last_five_rate=RateResponse.from_result(last_five),
                    last_ten_rate=RateResponse.from_result(last_ten),
                    current_streak=compute_streaks(lines).current,
                    valid_starts=summary.rate_for(1).valid,
                )
            )
        return PlayerComparisonResponse(items=items)
