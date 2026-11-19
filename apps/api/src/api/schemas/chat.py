import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.enums.chat import MessageRole


class AskRequest(BaseModel):
    # TODO: once auth exists, derive the workspace from the session instead of the body.
    workspace_id: uuid.UUID
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None  # omit to start a new conversation


class CitationOut(BaseModel):
    index: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    filename: str
    page_number: int | None = None
    heading_path: str | None = None
    snippet: str
    score: float


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[CitationOut] = []
    refused: bool
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]