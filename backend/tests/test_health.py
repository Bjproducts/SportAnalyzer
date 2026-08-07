"""Phase 1 smoke tests: the app boots and reports health honestly."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import database as database_module
from app.database import Database
from app.main import create_app
from app.version import VERSION


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_liveness_does_not_touch_the_database(client):
    """Liveness must succeed even with no database at all."""
    response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_health_reports_503_when_database_is_unreachable(client, monkeypatch):
    """An unreachable database must surface as 503 + 'degraded', never as 'ok'."""

    async def unavailable(_database: Database) -> bool:
        return False

    monkeypatch.setattr(Database, "healthcheck", unavailable)
    monkeypatch.setattr(database_module, "_database", None)

    response = await client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"


async def test_health_reports_ok_with_a_working_database(client, database: Database, monkeypatch):
    monkeypatch.setattr(database_module, "_database", database)

    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == VERSION == "1.1.0"
    assert body["uptime_seconds"] >= 0


async def test_root_lists_entrypoints(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["health"] == "/api/health"
    assert response.json()["players"] == "/api/players"


async def test_unknown_route_returns_structured_error(client):
    """404s use the same error envelope as everything else."""
    response = await client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


async def test_request_id_header_is_echoed(client):
    response = await client.get("/api/health/live", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
