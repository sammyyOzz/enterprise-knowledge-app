import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from api.enums.enums import ProcessingStatus
from api.services.ingestion import UploadOutcome


class UploadResponse(BaseModel):
  outcome: UploadOutcome
  document_id: uuid.UUID
  version_id: uuid.UUID
  version_number: int
  version_status: ProcessingStatus
  job_id: uuid.UUID | None = None


class VersionOut(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  id: uuid.UUID
  version_number: int
  status: ProcessingStatus
  file_size: int
  content_hash: str
  error_message: str | None = None
  created_at: datetime


class DocumentOut(BaseModel):
  id: uuid.UUID
  filename: str
  mime_type: str
  current_version: int
  status: ProcessingStatus | None = None  # status of the current version
  created_at: datetime
  updated_at: datetime


class DocumentDetailOut(DocumentOut):
  versions: list[VersionOut]