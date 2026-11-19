import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from api.enums.chat import MessageRole
from api.enums.enums import _enum


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Assistant messages only. `citations` is a snapshot of what was cited (file, page, heading,
    # snippet, score) so history stays correct even if the document is later re-versioned.
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # True when no reliable answer was given (nothing relevant retrieved, or answer cited nothing).
    refused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Observability (feeds the Phase 4 cost/latency dashboard).
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")