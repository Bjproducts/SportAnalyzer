"""Application orchestration for player search and SOT analytics."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import (
    build_sot_summary,
    compute_competition_split,
    compute_form_windows,
    compute_opponent_split,
    compute_season_split,
    compute_streaks,
    compute_venue_splits,
)
from app.core.exceptions import NotFoundError
from app.models import Player
from app.repositories.players import PlayerMatchQuery, PlayerMatchRepository, PlayerRepository
from app.schemas.players import (
    FormWindowResponse,
    PaginationMeta,
    PlayerDetail,
    PlayerMatch,
    PlayerMatchesResponse,
    PlayerSearchResponse,
    PlayerSotSummaryResponse,
    PlayerSplitsResponse,
    PlayerStreaksResponse,
    SotSummaryResponse,
    SplitEntryResponse,
    StreakResponse,
    VenueSplitsResponse,
    player_detail,
    player_list_item,
)


class PlayerAnalyticsService:
    """Coordinates repositories with the pure Phase 3 analytics engine."""

    def __init__(self, session: AsyncSession) -> None:
        self.players = PlayerRepository(session)
        self.matches = PlayerMatchRepository(session)

    async def _require_player(self, player_id: int) -> Player:
        player = await self.players.get(player_id)
        if player is None:
            raise NotFoundError("Player", player_id)
        return player

    async def search_players(
        self,
        query: str | None,
        *,
        page: int,
        page_size: int,
    ) -> PlayerSearchResponse:
        players, total = await self.players.search(
            query,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return PlayerSearchResponse(
            items=[player_list_item(player) for player in players],
            pagination=PaginationMeta.build(page=page, page_size=page_size, total=total),
        )

    async def get_player(self, player_id: int) -> PlayerDetail:
        return player_detail(await self._require_player(player_id))

    async def get_matches(
        self,
        player_id: int,
        query: PlayerMatchQuery,
        *,
        page: int,
        page_size: int,
    ) -> PlayerMatchesResponse:
        player = await self._require_player(player_id)
        total = await self.matches.count(player_id, query)
        lines = await self.matches.list(
            player_id,
            query,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return PlayerMatchesResponse(
            player=player_list_item(player),
            items=[PlayerMatch.from_line(line) for line in lines],
            pagination=PaginationMeta.build(page=page, page_size=page_size, total=total),
        )

    async def get_summary(
        self,
        player_id: int,
        query: PlayerMatchQuery,
    ) -> PlayerSotSummaryResponse:
        player = await self._require_player(player_id)
        lines = await self.matches.list(player_id, query)
        summary = build_sot_summary(lines, player_id=player_id)
        form = compute_form_windows(lines)
        return PlayerSotSummaryResponse(
            player=player_list_item(player),
            summary=SotSummaryResponse.from_result(summary),
            recent_form={
                window: FormWindowResponse.from_result(result) for window, result in form.items()
            },
        )

    async def get_splits(
        self,
        player_id: int,
        query: PlayerMatchQuery,
        *,
        threshold: int,
        minimum_starts: int,
    ) -> PlayerSplitsResponse:
        player = await self._require_player(player_id)
        lines = await self.matches.list(player_id, query)
        return PlayerSplitsResponse(
            player=player_list_item(player),
            threshold=threshold,
            venue=VenueSplitsResponse.from_result(compute_venue_splits(lines, threshold)),
            competitions=[
                SplitEntryResponse.from_result(entry)
                for entry in compute_competition_split(
                    lines,
                    threshold=threshold,
                    minimum_starts=minimum_starts,
                )
            ],
            seasons=[
                SplitEntryResponse.from_result(entry)
                for entry in compute_season_split(
                    lines,
                    threshold=threshold,
                    minimum_starts=minimum_starts,
                )
            ],
            opponents=[
                SplitEntryResponse.from_result(entry)
                for entry in compute_opponent_split(
                    lines,
                    threshold=threshold,
                    minimum_starts=minimum_starts,
                )
            ],
        )

    async def get_streaks(
        self,
        player_id: int,
        query: PlayerMatchQuery,
        *,
        threshold: int,
    ) -> PlayerStreaksResponse:
        player = await self._require_player(player_id)
        lines = await self.matches.list(player_id, query)
        return PlayerStreaksResponse(
            player=player_list_item(player),
            streak=StreakResponse.from_result(compute_streaks(lines, threshold)),
        )
