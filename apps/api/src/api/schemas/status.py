import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from api.enums.enums import IngestionStage, JobStatus, ProcessingStatus


class JobOut(BaseModel):
    """
    One processing attempt. The job's internal error text is deliberately NOT exposed
    (it can contain provider or stack details); the user-safe message is on the version.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt: int
    status: JobStatus
    stage: IngestionStage | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class VersionStatusOut(BaseModel):
    version_id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    status: ProcessingStatus
    error_message: str | None = None
    attempts: int
    latest_job: JobOut | None = None
    chunks_total: int
    chunks_embedded: int  # chunks_embedded / chunks_total = embedding progress