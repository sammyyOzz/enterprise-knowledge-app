import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
  __tablename__ = "workspaces"

  organization_id: Mapped[uuid.UUID] = mapped_column(
      ForeignKey("organizations.id", ondelete="CASCADE"), index=True
  )
  name: Mapped[str] = mapped_column(String(255), nullable=False)

  organization: Mapped["Organization"] = relationship(back_populates="workspaces")
  members: Mapped[list["WorkspaceMember"]] = relationship(
      back_populates="workspace", cascade="all, delete-orphan"
  )
  documents: Mapped[list["Document"]] = relationship(
      back_populates="workspace", cascade="all, delete-orphan"
  )