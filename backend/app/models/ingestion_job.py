"""Ingestion job log.

Every import attempt is recorded here, successful or not.  A failed import must
leave a row explaining why - "do not silently ignore failed imports" is a hard
requirement, and this table is how it is met.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import IngestionJobStatus, IngestionJobType
from app.database import Base, TimestampMixin
from app.models.types import JSONVariant, enum_column


class IngestionJob(Base, TimestampMixin):
    """One ingestion run."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("records_processed >= 0", name="records_processed_non_negative"),
        CheckConstraint("records_created >= 0", name="records_created_non_negative"),
        CheckConstraint("records_updated >= 0", name="records_updated_non_negative"),
        CheckConstraint("records_failed >= 0", name="records_failed_non_negative"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finished_after_started",
        ),
        # The admin jobs list is "most recent first", optionally by status.
        Index("ix_ingestion_jobs_status_created_at", "status", "created_at"),
        Index("ix_ingestion_jobs_job_type_created_at", "job_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    job_type: Mapped[IngestionJobType] = mapped_column(
        enum_column(IngestionJobType), nullable=False
    )
    status: Mapped[IngestionJobStatus] = mapped_column(
        enum_column(IngestionJobStatus), nullable=False, default=IngestionJobStatus.PENDING
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    #: Call parameters (competition id, season, fixture ids, ...). Stored so a
    #: failed job can be retried with exactly the same inputs.
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Human-readable failure reason. Never left empty on a failed job.
    error_message: Mapped[str | None] = mapped_column(Text)
    #: Structured per-record failures: [{"entity_id": ..., "reason": ...}, ...].
    #: Secrets are stripped before anything is written here.
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock runtime, or ``None`` while the job is still open."""
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def __repr__(self) -> str:
        return f"<IngestionJob id={self.id} type={self.job_type} status={self.status}>"
