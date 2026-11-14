from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    MetaData,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from api.core.config import config

import uuid
from datetime import datetime


# Synchronous engine: simple, and works the same in FastAPI routes and Celery tasks.
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# --------------------------------------------------------------------------- #
# Base + mixins
# --------------------------------------------------------------------------- #
class Base(DeclarativeBase):
  # Consistent constraint names make Alembic migrations predictable.
  metadata = MetaData(
    naming_convention={
      "ix": "ix_%(column_0_label)s",
      "uq": "uq_%(table_name)s_%(column_0_name)s",
      "ck": "ck_%(table_name)s_%(constraint_name)s",
      "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
      "pk": "pk_%(table_name)s",
    }
  )


class UUIDPrimaryKeyMixin:
  id: Mapped[uuid.UUID] = mapped_column(
      UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
  )


class TimestampMixin:
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), server_default=func.now(), nullable=False
  )
  updated_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      server_default=func.now(),
      onupdate=func.now(),
      nullable=False,
  )


# =========================================================================== #

def get_db() -> Iterator[Session]:
  """FastAPI dependency: one session per request."""
  db = SessionLocal()
  try:
      yield db
  finally:
    db.close()