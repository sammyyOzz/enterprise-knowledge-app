import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from api.enums.enums import UserRole, _enum


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
  __tablename__ = "users"

  organization_id: Mapped[uuid.UUID] = mapped_column(
      ForeignKey("organizations.id", ondelete="CASCADE"), index=True
  )
  email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
  hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
  full_name: Mapped[str | None] = mapped_column(String(255))
  role: Mapped[UserRole] = mapped_column(
      _enum(UserRole), default=UserRole.MEMBER, nullable=False
  )
  is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

  organization: Mapped["Organization"] = relationship(back_populates="users")
