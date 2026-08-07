"""Load the deterministic demo competition through the real ingestion path."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.database import init_database
from app.ingestion.fake import FakeFootballProvider
from app.ingestion.service import IngestionService
from app.models import Fixture


async def seed() -> None:
    database = init_database(get_settings())
    async with database.session() as session:
        await IngestionService(session, FakeFootballProvider()).ingest_fixtures(9001, 2025)
        fixture_ids = list((await session.scalars(select(Fixture.id))).all())
        await IngestionService(session, FakeFootballProvider()).ingest_player_statistics(
            fixture_ids
        )


if __name__ == "__main__":
    asyncio.run(seed())
