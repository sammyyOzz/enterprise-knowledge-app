import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
  """A logical document. Each upload of changed content adds a DocumentVersion."""

  __tablename__ = "documents"
  __table_args__ = (
      # Same filename in the same workspace = a new version of the same document.
      UniqueConstraint("workspace_id", "filename", name="uq_documents_workspace_filename"),
  )

  workspace_id: Mapped[uuid.UUID] = mapped_column(
      ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
  )
  uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
      ForeignKey("users.id", ondelete="SET NULL")
  )
  filename: Mapped[str] = mapped_column(String(500), nullable=False)
  mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
  current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

  workspace: Mapped["Workspace"] = relationship(back_populates="documents")
  versions: Mapped[list["DocumentVersion"]] = relationship(
      back_populates="document",
      cascade="all, delete-orphan",
      order_by="DocumentVersion.version_number",
  )