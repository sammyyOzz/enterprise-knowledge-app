import uuid

from sqlalchemy import (
    DateTime,
    Integer,
    Text,
    ForeignKey, 
    String
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from api.enums.enums import JobStatus, IngestionStage, _enum



class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One processing attempt of a document version (retries create new jobs)."""

    __tablename__ = "ingestion_jobs"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus), default=JobStatus.QUEUED, nullable=False
    )
    stage: Mapped[IngestionStage | None] = mapped_column(_enum(IngestionStage))
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="jobs")