"""Administrative ingestion request and job-log schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import IngestionJobStatus, IngestionJobType


class FixtureIngestionRequest(BaseModel):
    provider_competition_id: Annotated[int, Field(gt=0)]
    season: Annotated[int, Field(ge=1850, le=2200)]


class PlayerStatisticsIngestionRequest(BaseModel):
    fixture_ids: Annotated[list[int], Field(min_length=1, max_length=100)]


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: IngestionJobType
    status: IngestionJobStatus
    provider: str
    parameters: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    records_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    error_message: str | None
    error_details: dict[str, Any] | None
    duration_seconds: float | None


class IngestionJobsResponse(BaseModel):
    items: list[IngestionJobResponse]
    total: int


class TrackedLeagueResponse(BaseModel):
    slug: str
    provider_id: int
    name: str
    country: str
    calendar_year_season: bool


class TrackedLeaguesResponse(BaseModel):
    items: list[TrackedLeagueResponse]
