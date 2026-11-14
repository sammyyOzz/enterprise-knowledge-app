import enum
from sqlalchemy import Enum

class UserRole(str, enum.Enum):
  ADMIN = "admin"
  MEMBER = "member"


class WorkspaceRole(str, enum.Enum):
  OWNER = "owner"
  EDITOR = "editor"
  VIEWER = "viewer"


class ProcessingStatus(str, enum.Enum):
  PENDING = "pending"
  PROCESSING = "processing"
  READY = "ready"
  FAILED = "failed"


class JobStatus(str, enum.Enum):
  QUEUED = "queued"
  RUNNING = "running"
  SUCCEEDED = "succeeded"
  FAILED = "failed"


class IngestionStage(str, enum.Enum):
  PARSING = "parsing"
  CHUNKING = "chunking"
  EMBEDDING = "embedding"
  INDEXING = "indexing"
  DONE = "done"


def _enum(enum_cls: type[enum.Enum]) -> Enum:
    """String-backed enum using the enum *values* (not names)."""
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
        length=32,
    )
