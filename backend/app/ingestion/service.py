"""Idempotent fixture and player-stat ingestion with persistent job logs."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CompetitionType,
    IngestionJobStatus,
    IngestionJobType,
    PositionGroup,
    PreferredFoot,
)
from app.ingestion.provider import (
    FootballDataProvider,
    ProviderFixture,
    ProviderPlayer,
    ProviderPlayerStat,
    ProviderTeam,
)
from app.models import (
    Competition,
    Fixture,
    IngestionJob,
    Player,
    PlayerFixtureStats,
    Season,
    Team,
)


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        provider: FootballDataProvider,
        *,
        close_provider: bool = True,
    ) -> None:
        self.session = session
        self.provider = provider
        self.close_provider = close_provider

    async def _start_job(
        self, job_type: IngestionJobType, parameters: dict[str, object]
    ) -> IngestionJob:
        job = IngestionJob(
            job_type=job_type,
            status=IngestionJobStatus.RUNNING,
            provider=self.provider.name,
            parameters=parameters,
            started_at=datetime.now(UTC),
            records_processed=0,
            records_created=0,
            records_updated=0,
            records_failed=0,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def _fail_job(self, job_id: int, exc: Exception) -> None:
        await self.session.rollback()
        job = await self.session.get(IngestionJob, job_id)
        if job is not None:
            job.status = IngestionJobStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            job.records_failed = max(job.records_failed, 1)
            await self.session.commit()

    async def ingest_fixtures(self, competition_id: int, season_year: int) -> IngestionJob:
        job = await self._start_job(
            IngestionJobType.FIXTURES,
            {"provider_competition_id": competition_id, "season": season_year},
        )
        try:
            fixtures = await self.provider.get_fixtures(competition_id, season_year)
            created = 0
            updated = 0
            for item in fixtures:
                was_created = await self._upsert_fixture(item)
                created += int(was_created)
                updated += int(not was_created)
            job.records_processed = len(fixtures)
            job.records_created = created
            job.records_updated = updated
            job.status = IngestionJobStatus.SUCCEEDED
            job.finished_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(job)
            return job
        except Exception as exc:
            await self._fail_job(job.id, exc)
            raise
        finally:
            if self.close_provider:
                await self.provider.aclose()

    async def ingest_player_statistics(self, fixture_ids: list[int]) -> IngestionJob:
        job = await self._start_job(
            IngestionJobType.PLAYER_STATISTICS,
            {"fixture_ids": fixture_ids},
        )
        created = 0
        updated = 0
        failures: list[dict[str, object]] = []
        try:
            for fixture_id in fixture_ids:
                fixture = await self.session.get(Fixture, fixture_id)
                if fixture is None:
                    failures.append({"fixture_id": fixture_id, "reason": "Fixture not found"})
                    continue
                home_team = await self.session.get(Team, fixture.home_team_id)
                away_team = await self.session.get(Team, fixture.away_team_id)
                if home_team is None or away_team is None:
                    failures.append({"fixture_id": fixture_id, "reason": "Fixture teams not found"})
                    continue
                try:
                    rows = await self.provider.get_player_fixture_statistics(
                        fixture.provider_fixture_id,
                        home_team_id=home_team.provider_team_id,
                        away_team_id=away_team.provider_team_id,
                    )
                except Exception as exc:
                    # Coverage can vary match by match even within one league.
                    # Record the unavailable fixture and continue so one 404
                    # cannot prevent every later league from being imported.
                    failures.append(
                        {
                            "fixture_id": fixture_id,
                            "provider_fixture_id": fixture.provider_fixture_id,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        }
                    )
                    continue
                for row in rows:
                    try:
                        async with self.session.begin_nested():
                            was_created = await self._upsert_player_stat(fixture, row)
                            await self.session.flush()
                        created += int(was_created)
                        updated += int(not was_created)
                    except Exception as exc:
                        failures.append(
                            {
                                "fixture_id": fixture_id,
                                "player_id": row.player.id,
                                "reason": f"{type(exc).__name__}: {exc}"[:500],
                            }
                        )
            job.records_processed = created + updated + len(failures)
            job.records_created = created
            job.records_updated = updated
            job.records_failed = len(failures)
            job.error_details = {"failures": failures} if failures else None
            job.error_message = "Some records failed validation." if failures else None
            job.status = IngestionJobStatus.PARTIAL if failures else IngestionJobStatus.SUCCEEDED
            job.finished_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(job)
            return job
        except Exception as exc:
            await self._fail_job(job.id, exc)
            raise
        finally:
            if self.close_provider:
                await self.provider.aclose()

    async def _upsert_fixture(self, item: ProviderFixture) -> bool:
        competition = await self.session.scalar(
            select(Competition).where(Competition.provider_competition_id == item.competition.id)
        )
        if competition is None:
            competition = Competition(
                provider_competition_id=item.competition.id,
                name=item.competition.name,
                country=item.competition.country,
                logo_url=item.competition.logo_url,
                competition_type=CompetitionType.LEAGUE,
                is_competitive=True,
            )
            self.session.add(competition)
            await self.session.flush()
        else:
            competition.name = item.competition.name
            competition.country = item.competition.country
            competition.logo_url = item.competition.logo_url

        season = await self.session.scalar(
            select(Season).where(
                Season.competition_id == competition.id,
                Season.season_year == item.season_year,
            )
        )
        if season is None:
            season = Season(
                competition=competition,
                season_year=item.season_year,
                label=item.season_label,
                is_current=False,
            )
            self.session.add(season)
            await self.session.flush()

        home = await self._upsert_team(item.home_team)
        away = await self._upsert_team(item.away_team)
        fixture = await self.session.scalar(
            select(Fixture).where(Fixture.provider_fixture_id == item.id)
        )
        created = fixture is None
        if fixture is None:
            fixture = Fixture(provider_fixture_id=item.id)
            self.session.add(fixture)
        fixture.competition = competition
        fixture.season = season
        fixture.fixture_date = item.fixture_date
        fixture.home_team = home
        fixture.away_team = away
        fixture.home_score = item.home_score
        fixture.away_score = item.away_score
        fixture.status = item.status
        fixture.venue = item.venue
        fixture.round = item.round
        fixture.last_synced_at = datetime.now(UTC)
        await self.session.flush()
        return created

    async def _upsert_team(self, item: ProviderTeam) -> Team:
        team = await self.session.scalar(select(Team).where(Team.provider_team_id == item.id))
        if team is None:
            team = Team(provider_team_id=item.id, name=item.name)
            self.session.add(team)
        team.name = item.name
        team.short_name = item.short_name
        team.country = item.country
        team.logo_url = item.logo_url
        team.apply_search_name()
        await self.session.flush()
        return team

    async def _upsert_player_stat(self, fixture: Fixture, item: ProviderPlayerStat) -> bool:
        team = await self.session.scalar(select(Team).where(Team.provider_team_id == item.team_id))
        opponent = await self.session.scalar(
            select(Team).where(Team.provider_team_id == item.opponent_id)
        )
        if team is None or opponent is None:
            raise ValueError("Player statistics referenced a team that was not ingested.")
        player = await self._upsert_player(item.player, team, fixture.fixture_date)
        stats = await self.session.scalar(
            select(PlayerFixtureStats).where(
                PlayerFixtureStats.fixture_id == fixture.id,
                PlayerFixtureStats.player_id == player.id,
                PlayerFixtureStats.team_id == team.id,
            )
        )
        created = stats is None
        if stats is None:
            stats = PlayerFixtureStats(fixture=fixture, player=player, team=team)
            self.session.add(stats)
        stats.opponent = opponent
        stats.home = item.home
        stats.started = item.started
        stats.substitute_appearance = item.substitute_appearance
        stats.minutes_played = item.minutes_played
        stats.position = item.position
        stats.shirt_number = item.shirt_number
        stats.shots = item.shots
        stats.shots_on_target = item.shots_on_target
        stats.goals = item.goals
        stats.assists = item.assists
        stats.key_passes = item.key_passes
        stats.touches = item.touches
        stats.rating = item.rating
        stats.team_shots = item.team_shots
        stats.team_shots_on_target = item.team_shots_on_target
        stats.data_source = self.provider.name
        stats.data_quality_status = item.data_quality_status
        stats.provider_raw_data = item.raw
        stats.apply_derived_fields()
        return created

    async def _upsert_player(
        self,
        item: ProviderPlayer,
        team: Team,
        fixture_date: datetime,
    ) -> Player:
        player = await self.session.scalar(
            select(Player).where(Player.provider_player_id == item.id)
        )
        latest_fixture_date = None
        if player is None:
            player = Player(provider_player_id=item.id, full_name=item.full_name)
            self.session.add(player)
        else:
            latest_fixture_date = await self.session.scalar(
                select(func.max(Fixture.fixture_date))
                .join(PlayerFixtureStats, PlayerFixtureStats.fixture_id == Fixture.id)
                .where(PlayerFixtureStats.player_id == player.id)
            )
        player.full_name = item.full_name
        player.common_name = item.common_name
        player.date_of_birth = item.date_of_birth
        player.nationality = item.nationality
        player.primary_position = item.position
        player.position_group = self._position_group(item.position)
        player.preferred_foot = self._preferred_foot(item.preferred_foot)
        if latest_fixture_date is None or self._utc(fixture_date) >= self._utc(latest_fixture_date):
            player.current_team = team
        player.photo_url = item.photo_url
        player.apply_search_names()
        await self.session.flush()
        return player

    @staticmethod
    def _position_group(position: str | None) -> PositionGroup:
        value = (position or "").casefold()
        if value in {"g", "gk", "goalkeeper"}:
            return PositionGroup.GOALKEEPER
        if value in {"d", "cb", "lb", "rb", "defender"}:
            return PositionGroup.DEFENDER
        if value in {"m", "cm", "dm", "am", "midfielder"}:
            return PositionGroup.MIDFIELDER
        if value in {"f", "fw", "st", "cf", "lw", "rw", "attacker"}:
            return PositionGroup.ATTACKER
        return PositionGroup.UNKNOWN

    @staticmethod
    def _preferred_foot(value: str | None) -> PreferredFoot:
        normalized = (value or "").casefold()
        return {
            "left": PreferredFoot.LEFT,
            "right": PreferredFoot.RIGHT,
            "both": PreferredFoot.BOTH,
        }.get(normalized, PreferredFoot.UNKNOWN)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
