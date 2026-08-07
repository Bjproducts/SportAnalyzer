"""Provider clients, normalisation and ingestion jobs."""

from app.ingestion.factory import create_provider
from app.ingestion.leagues import TRACKED_LEAGUES, TrackedLeague, resolve_leagues
from app.ingestion.provider import FootballDataProvider
from app.ingestion.service import IngestionService
from app.ingestion.sync import LeagueSyncReport, LeagueSyncSummary, sync_leagues

__all__ = [
    "TRACKED_LEAGUES",
    "FootballDataProvider",
    "IngestionService",
    "LeagueSyncReport",
    "LeagueSyncSummary",
    "TrackedLeague",
    "create_provider",
    "resolve_leagues",
    "sync_leagues",
]
