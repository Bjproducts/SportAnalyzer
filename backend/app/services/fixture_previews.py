"""Upcoming fixture orchestration over stored, provider-authorized data."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.analytics import build_sot_summary, compute_venue_splits
from app.analytics.preview import CandidatePreviewInput, score_candidate
from app.core.enums import FixtureStatus, Venue
from app.models import Competition, Fixture, Player, PlayerFixtureStats, Team
from app.repositories.players import PlayerMatchQuery, PlayerMatchRepository
from app.schemas.fixtures import FixtureResponse
from app.schemas.players import RateResponse, TeamBrief, player_list_item
from app.schemas.previews import (
    DailyFixtureAnalysisResponse,
    DefensiveContextResponse,
    FixtureCandidateResponse,
    FixturePreviewResponse,
    TeamFixturePreviewResponse,
)


class FixturePreviewService:
    """Build daily previews without making live provider calls."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.matches = PlayerMatchRepository(session)
        self._defense_cache: dict[tuple[int, int], DefensiveContextResponse] = {}

    async def daily(
        self,
        analysis_date: date,
        *,
        window: Literal[5, 10, 20],
        candidates_per_team: int,
    ) -> DailyFixtureAnalysisResponse:
        start = datetime.combine(analysis_date, time.min, UTC)
        end = start + timedelta(days=1)
        statement = (
            select(Fixture)
            .options(
                joinedload(Fixture.competition),
                joinedload(Fixture.season),
                joinedload(Fixture.home_team),
                joinedload(Fixture.away_team),
            )
            .where(
                Fixture.fixture_date >= start,
                Fixture.fixture_date < end,
                Fixture.status == FixtureStatus.SCHEDULED,
            )
            .order_by(Fixture.fixture_date, Fixture.id)
        )
        fixtures = list((await self.session.scalars(statement)).unique().all())
        previews: list[FixturePreviewResponse] = []
        for fixture in fixtures:
            home_defense = await self._defensive_context(fixture.home_team, window)
            away_defense = await self._defensive_context(fixture.away_team, window)
            home = await self._team_preview(
                fixture.home_team,
                fixture.away_team,
                Venue.HOME,
                away_defense,
                window,
                candidates_per_team,
            )
            away = await self._team_preview(
                fixture.away_team,
                fixture.home_team,
                Venue.AWAY,
                home_defense,
                window,
                candidates_per_team,
            )
            previews.append(
                FixturePreviewResponse(
                    fixture=FixtureResponse.model_validate(fixture),
                    home=home,
                    away=away,
                )
            )

        return DailyFixtureAnalysisResponse(
            date=analysis_date,
            generated_at=datetime.now(UTC),
            window=window,
            fixtures=previews,
            methodology=(
                "Research score (0-100): recent 1+ SOT rate 35%, sample-adjusted "
                "reliability 20%, SOT volume 15%, venue record 10%, minutes stability "
                "10%, and opponent SOT allowed 10%."
            ),
            disclaimer=(
                "This is an evidence ranking, not a probability or guarantee. Starting "
                "lineups, injuries, tactical roles and late fixture changes are not confirmed."
            ),
        )

    async def _team_preview(
        self,
        team: Team,
        opponent: Team,
        venue: Venue,
        opponent_defense: DefensiveContextResponse,
        window: Literal[5, 10, 20],
        limit: int,
    ) -> TeamFixturePreviewResponse:
        squad_statement = (
            select(Player)
            .options(joinedload(Player.current_team))
            .where(Player.current_team_id == team.id)
            .order_by(Player.search_common_name, Player.id)
        )
        squad = list((await self.session.scalars(squad_statement)).unique().all())
        candidates: list[FixtureCandidateResponse] = []
        for player in squad:
            lines = await self.matches.list(
                player.id,
                PlayerMatchQuery(starts_only=True, team_id=team.id, last_n=window),
            )
            summary = build_sot_summary(lines, player_id=player.id)
            recent = summary.rate_for(1)
            venues = compute_venue_splits(lines)
            venue_rate = venues.home if venue is Venue.HOME else venues.away
            minutes = summary.minutes
            preview_score = score_candidate(
                CandidatePreviewInput(
                    recent_rate=recent,
                    venue_rate=venue_rate,
                    average_sot=summary.average_sot_per_start,
                    average_minutes=(minutes.average_minutes_per_start if minutes else None),
                    pct_at_least_80=(minutes.pct_at_least_80 if minutes else None),
                    opponent_average_sot_allowed=opponent_defense.average_sot_allowed,
                    opponent_defense_matches=opponent_defense.matches,
                )
            )
            candidates.append(
                FixtureCandidateResponse(
                    rank=0,
                    research_score=preview_score.score,
                    score_label=preview_score.label,
                    confidence=preview_score.confidence,
                    player=player_list_item(player),
                    recent_rate=RateResponse.from_result(recent),
                    venue_rate=RateResponse.from_result(venue_rate),
                    average_sot=summary.average_sot_per_start,
                    average_minutes=(minutes.average_minutes_per_start if minutes else None),
                    reasons=list(preview_score.reasons),
                    risks=list(preview_score.risks),
                )
            )

        candidates.sort(
            key=lambda candidate: (
                -candidate.research_score,
                -candidate.recent_rate.valid,
                candidate.player.display_name.casefold(),
                candidate.player.id,
            )
        )
        ranked = [
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(candidates[:limit], start=1)
        ]
        warning = None
        if not squad:
            warning = "No current squad is stored for this team."
        elif not any(candidate.recent_rate.valid for candidate in ranked):
            warning = "Current squad is stored, but recent player SOT evidence is unavailable."
        return TeamFixturePreviewResponse(
            team=TeamBrief.model_validate(team),
            opponent=TeamBrief.model_validate(opponent),
            venue=venue,
            opponent_defense=opponent_defense,
            candidates=ranked,
            warning=warning,
        )

    async def _defensive_context(
        self,
        team: Team,
        window: Literal[5, 10, 20],
    ) -> DefensiveContextResponse:
        cache_key = (team.id, window)
        cached = self._defense_cache.get(cache_key)
        if cached is not None:
            return cached

        statement = (
            select(
                Fixture.id,
                Fixture.fixture_date,
                PlayerFixtureStats.team_shots_on_target,
            )
            .select_from(PlayerFixtureStats)
            .join(Fixture, PlayerFixtureStats.fixture_id == Fixture.id)
            .join(Competition, Fixture.competition_id == Competition.id)
            .where(
                PlayerFixtureStats.opponent_id == team.id,
                PlayerFixtureStats.team_shots_on_target.is_not(None),
                Fixture.status == FixtureStatus.FINISHED,
                Competition.is_competitive.is_(True),
            )
            .order_by(Fixture.fixture_date.desc(), Fixture.id.desc())
        )
        rows = (await self.session.execute(statement)).all()
        values: list[int] = []
        seen_fixtures: set[int] = set()
        for fixture_id, _fixture_date, team_sot in rows:
            if fixture_id in seen_fixtures or team_sot is None:
                continue
            seen_fixtures.add(fixture_id)
            values.append(int(team_sot))
            if len(values) >= window:
                break

        average = round(sum(values) / len(values), 2) if values else None
        if average is None:
            label: Literal["strong", "neutral", "vulnerable", "unknown"] = "unknown"
            description = "No recent opponent SOT-allowed evidence is stored."
        elif average <= 3.5:
            label = "strong"
            description = f"Strong recent defense: {average:.1f} opponent SOT allowed per match."
        elif average >= 5.0:
            label = "vulnerable"
            description = (
                f"Permissive recent defense: {average:.1f} opponent SOT allowed per match."
            )
        else:
            label = "neutral"
            description = f"Neutral recent defense: {average:.1f} opponent SOT allowed per match."

        context = DefensiveContextResponse(
            team=TeamBrief.model_validate(team),
            average_sot_allowed=average,
            matches=len(values),
            label=label,
            description=description,
        )
        self._defense_cache[cache_key] = context
        return context
