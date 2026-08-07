"""Phase 6/7 integration tests: ingestion, rankings, comparisons and fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as database_module
from app.core.enums import FixtureStatus, IngestionJobStatus
from app.core.exceptions import ProviderError
from app.database import Database
from app.ingestion.fake import FakeFootballProvider
from app.ingestion.rate_limit import RateLimiter
from app.ingestion.service import IngestionService
from app.main import create_app
from app.models import Fixture, Player, PlayerFixtureStats, Team


async def _seed(session: AsyncSession) -> tuple[int, list[int], list[int]]:
    fixture_job = await IngestionService(session, FakeFootballProvider()).ingest_fixtures(
        9001, 2025
    )
    assert fixture_job.status is IngestionJobStatus.SUCCEEDED
    fixture_ids = list((await session.scalars(select(Fixture.id).order_by(Fixture.id))).all())
    stats_job = await IngestionService(session, FakeFootballProvider()).ingest_player_statistics(
        fixture_ids
    )
    assert stats_job.status is IngestionJobStatus.SUCCEEDED
    team_id = int(await session.scalar(select(Team.id).where(Team.provider_team_id == 42)) or 0)
    player_ids = list((await session.scalars(select(Player.id).order_by(Player.id))).all())
    return team_id, fixture_ids, player_ids


async def test_fake_provider_ingestion_loads_a_complete_demo_season(session):
    team_id, fixture_ids, player_ids = await _seed(session)

    assert team_id > 0
    assert len(fixture_ids) == 12
    assert len(player_ids) == 6
    assert await session.scalar(select(func.count(PlayerFixtureStats.id))) == 72
    missing = await session.scalar(
        select(func.count(PlayerFixtureStats.id)).where(
            PlayerFixtureStats.shots_on_target.is_(None)
        )
    )
    assert missing == 1


async def test_ingestion_is_idempotent_and_reports_updates(session):
    _, fixture_ids, _ = await _seed(session)

    fixture_job = await IngestionService(session, FakeFootballProvider()).ingest_fixtures(
        9001, 2025
    )
    stats_job = await IngestionService(session, FakeFootballProvider()).ingest_player_statistics(
        fixture_ids
    )

    assert fixture_job.records_created == 0
    assert fixture_job.records_updated == 12
    assert stats_job.records_created == 0
    assert stats_job.records_updated == 72
    assert await session.scalar(select(func.count(PlayerFixtureStats.id))) == 72


async def test_missing_fixture_is_recorded_as_a_partial_job(session):
    job = await IngestionService(session, FakeFootballProvider()).ingest_player_statistics([999999])

    assert job.status is IngestionJobStatus.PARTIAL
    assert job.records_failed == 1
    assert job.error_details is not None


async def test_provider_failure_is_recorded_without_aborting_later_fixtures(session):
    await IngestionService(session, FakeFootballProvider()).ingest_fixtures(9001, 2025)
    fixtures = list((await session.scalars(select(Fixture).order_by(Fixture.id))).all())

    class OneFixtureFailureProvider(FakeFootballProvider):
        async def get_player_fixture_statistics(
            self,
            fixture_id: int,
            *,
            home_team_id: int | None = None,
            away_team_id: int | None = None,
        ):
            if fixture_id == fixtures[0].provider_fixture_id:
                raise ProviderError("No match coverage.", provider=self.name, status_code=404)
            return await super().get_player_fixture_statistics(
                fixture_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
            )

    job = await IngestionService(session, OneFixtureFailureProvider()).ingest_player_statistics(
        [fixture.id for fixture in fixtures]
    )

    assert job.status is IngestionJobStatus.PARTIAL
    assert job.records_failed == 1
    assert job.records_created == 66
    assert await session.scalar(select(func.count(PlayerFixtureStats.id))) == 66


async def test_rate_limiter_waits_only_when_the_next_slot_is_in_the_future():
    now = [0.0]
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(60, clock=lambda: now[0], sleep=sleep)
    await limiter.acquire()
    await limiter.acquire()

    assert waits == [1.0]


@pytest.fixture
async def seeded_client(database: Database, session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    team_id, fixture_ids, player_ids = await _seed(session)
    monkeypatch.setattr(database_module, "_database", database)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client, team_id, fixture_ids, player_ids


async def test_team_rankings_apply_minimum_sample_and_sample_adjustment(seeded_client):
    client, team_id, _, _ = seeded_client
    response = await client.get(f"/api/teams/{team_id}/sot-rankings")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 5
    assert body["last_n"] == 5
    assert body["limit"] == 5
    assert body["items"][0]["eligible"] is True
    assert body["items"][0]["sample_adjusted_rate"] is not None
    assert all(item["rate"]["valid"] >= 0 for item in body["items"])

    full = await client.get(
        f"/api/teams/{team_id}/sot-rankings",
        params={"last_n": 10, "limit": 100},
    )
    assert len(full.json()["items"]) == 6
    assert full.json()["last_n"] == 10
    assert full.json()["items"][-1]["eligible"] is False


async def test_team_squad_and_venue_rankings(seeded_client):
    client, team_id, _, _ = seeded_client
    squad = await client.get(f"/api/teams/{team_id}/players")
    away = await client.get(
        f"/api/teams/{team_id}/sot-rankings", params={"venue": "away", "minimum_starts": 1}
    )

    assert len(squad.json()["items"]) == 6
    assert away.status_code == 200
    assert away.json()["venue"] == "away"


async def test_team_listing_prioritizes_populated_squads(seeded_client):
    client, team_id, _, _ = seeded_client
    response = await client.get("/api/teams", params={"page_size": 1})

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == team_id


async def test_player_comparison_displays_every_percentage_with_a_sample(seeded_client):
    client, _, _, player_ids = seeded_client
    response = await client.get(
        "/api/players/compare",
        params=[("player_ids", player_ids[0]), ("player_ids", player_ids[1])],
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["one_plus_rate"]["valid"] == items[0]["valid_starts"]
    assert "valid" in items[0]["home_rate"]
    assert "valid" in items[0]["last_five_rate"]


async def test_comparison_rejects_duplicate_players(seeded_client):
    client, _, _, player_ids = seeded_client
    response = await client.get(
        "/api/players/compare",
        params=[("player_ids", player_ids[0]), ("player_ids", player_ids[0])],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_fixture_list_and_detail(seeded_client):
    client, _, fixture_ids, _ = seeded_client
    listing = await client.get("/api/fixtures", params={"season": 2025, "page_size": 3})
    detail = await client.get(f"/api/fixtures/{fixture_ids[0]}")

    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 12
    assert len(listing.json()["items"]) == 3
    assert detail.status_code == 200
    assert detail.json()["competition"]["name"] == "SOT Demo League"


async def test_upcoming_fixture_analysis_ranks_both_sides_from_stored_evidence(
    database: Database,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, fixture_ids, _ = await _seed(session)
    template = await session.get(Fixture, fixture_ids[0])
    assert template is not None
    session.add(
        Fixture(
            provider_fixture_id=987654321,
            competition_id=template.competition_id,
            season_id=template.season_id,
            fixture_date=datetime(2030, 1, 15, 19, 30, tzinfo=UTC),
            home_team_id=template.home_team_id,
            away_team_id=template.away_team_id,
            status=FixtureStatus.SCHEDULED,
            venue="Research Ground",
            round="Preview round",
        )
    )
    await session.commit()

    monkeypatch.setattr(database_module, "_database", database)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/fixtures/upcoming-analysis",
            params={"date": "2030-01-15", "window": 5, "candidates_per_team": 5},
        )
        invalid_window = await client.get(
            "/api/fixtures/upcoming-analysis",
            params={"date": "2030-01-15", "window": 7},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2030-01-15"
    assert body["window"] == 5
    assert len(body["fixtures"]) == 1
    preview = body["fixtures"][0]
    assert len(preview["home"]["candidates"]) == 5
    assert preview["home"]["candidates"][0]["research_score"] >= 0
    assert preview["home"]["candidates"][0]["reasons"]
    assert preview["home"]["candidates"][0]["risks"]
    assert "probability" in body["disclaimer"]
    assert invalid_window.status_code == 422


async def test_admin_ingestion_requires_token_and_lists_jobs(seeded_client):
    client, _, _, _ = seeded_client
    rejected = await client.get("/api/admin/ingestion/jobs")
    accepted = await client.get(
        "/api/admin/ingestion/jobs", headers={"X-Admin-Token": "test-admin-token"}
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["total"] == 2


async def test_admin_fixture_ingestion_is_callable_with_fake_provider(
    database: Database, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(database_module, "_database", database)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/admin/ingestion/fixtures",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"provider_competition_id": 9001, "season": 2025},
        )

    assert response.status_code == 200
    assert response.json()["records_created"] == 12
    assert response.json()["status"] == "succeeded"


async def test_admin_league_catalog_lists_supported_live_competitions(
    database: Database, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(database_module, "_database", database)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/admin/ingestion/leagues",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 7
    assert response.json()["items"][0]["slug"] == "mls"
