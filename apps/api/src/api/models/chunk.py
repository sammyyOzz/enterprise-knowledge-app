import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from api.core.config import app_config



class Chunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_chunks_version_index"),
        # Approximate nearest-neighbour search (cosine distance).
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Keyword / BM25-style search.
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    # Denormalised on purpose, see module docstring.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)

    # Citation info
    page_number: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[str | None] = mapped_column(Text)  # e.g. "Leave Policy > Annual Leave"

    # Free-form extra metadata. Attribute is `meta` because `metadata` is reserved
    # by SQLAlchemy's declarative base; the DB column is still called "metadata".
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Nullable: chunks are inserted before embeddings are generated.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(app_config.EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))

    # Generated column for full-text search, maintained by Postgres.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="chunks")
