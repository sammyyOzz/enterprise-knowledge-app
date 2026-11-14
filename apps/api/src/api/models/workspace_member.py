import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, TimestampMixin
from api.enums.enums import WorkspaceRole, _enum

class WorkspaceMember(TimestampMixin, Base):
  __tablename__ = "workspace_members"

  workspace_id: Mapped[uuid.UUID] = mapped_column(
      ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
  )
  user_id: Mapped[uuid.UUID] = mapped_column(
      ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
  )
  role: Mapped[WorkspaceRole] = mapped_column(
      _enum(WorkspaceRole), default=WorkspaceRole.VIEWER, nullable=False
  )

  workspace: Mapped["Workspace"] = relationship(back_populates="members")
  user: Mapped["User"] = relationship()
