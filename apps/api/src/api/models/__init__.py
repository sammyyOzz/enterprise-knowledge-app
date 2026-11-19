"""
Import every model here so SQLAlchemy's registry knows about all of them.

Relationships reference each other by string name (e.g. relationship("Document")),
which only resolves once every model module has been imported. Importing any
`api.models.*` submodule runs this file first, so the registry is always complete.
"""

from api.models.organization import Organization
from api.models.user import User
from api.models.workspace import Workspace
from api.models.workspace_member import WorkspaceMember
from api.models.document import Document
from api.models.document_version import DocumentVersion
from api.models.chunk import Chunk
from api.models.ingestion_job import IngestionJob
from api.models.conversation import Conversation
from api.models.message import Message

__all__ = [
  "Organization",
  "User",
  "Workspace",
  "WorkspaceMember",
  "Document",
  "DocumentVersion",
  "Chunk",
  "IngestionJob",
  "Conversation",
  "Message",
]