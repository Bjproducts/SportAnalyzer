"""Contracts for date-based upcoming fixture research."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import Venue
from app.schemas.fixtures import FixtureResponse
from app.schemas.players import PlayerListItem, RateResponse, TeamBrief


class DefensiveContextResponse(BaseModel):
    team: TeamBrief
    average_sot_allowed: float | None
    matches: int
    label: Literal["strong", "neutral", "vulnerable", "unknown"]
    description: str


class FixtureCandidateResponse(BaseModel):
    rank: int
    research_score: int
    score_label: Literal["strong", "viable", "speculative"]
    confidence: Literal["high", "medium", "low"]
    player: PlayerListItem
    recent_rate: RateResponse
    venue_rate: RateResponse
    average_sot: float | None
    average_minutes: float | None
    reasons: list[str]
    risks: list[str]


class TeamFixturePreviewResponse(BaseModel):
    team: TeamBrief
    opponent: TeamBrief
    venue: Venue
    opponent_defense: DefensiveContextResponse
    candidates: list[FixtureCandidateResponse]
    warning: str | None = None


class FixturePreviewResponse(BaseModel):
    fixture: FixtureResponse
    home: TeamFixturePreviewResponse
    away: TeamFixturePreviewResponse


class DailyFixtureAnalysisResponse(BaseModel):
    date: date
    timezone: Literal["UTC"] = "UTC"
    generated_at: datetime
    window: Literal[5, 10, 20]
    fixtures: list[FixturePreviewResponse]
    methodology: str
    disclaimer: str
