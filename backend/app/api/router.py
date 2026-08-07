"""Aggregate API router.

Each feature area lives in its own module under ``app.api.routes`` and is
mounted here.  ``app.main`` only ever sees this single router.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import fixtures, health, ingestion, players, teams

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(players.router)
api_router.include_router(teams.router)
api_router.include_router(fixtures.router)
api_router.include_router(ingestion.router)
