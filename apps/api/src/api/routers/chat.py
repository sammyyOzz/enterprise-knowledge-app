import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import api.models  # noqa: F401  (registers all models)
from api.core.config import app_config
from api.core.database import get_db
from api.models.conversation import Conversation
from api.models.workspace import Workspace
from api.schemas.chat import AskRequest, ConversationDetailOut, ConversationOut
from api.services.chat import (
    ConversationNotFound,
    add_user_message,
    get_or_create_conversation,
    load_history,
    stream_answer,
)

router = APIRouter(prefix="/conversations", tags=["chat"])


def _sse(events: Iterator[dict]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/ask")
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    """
    Ask a question. Streams server-sent events, each a JSON object on a `data:` line:
      {"type": "meta",  "conversation_id": "..."}                      first
      {"type": "token", "text": "..."}                                 many
      {"type": "done",  "message_id", "answer", "citations", "refused"}  last (replace streamed text with `answer`)
      {"type": "error", "message": "..."}                              instead of done, if it failed
    """
    if db.get(Workspace, payload.workspace_id) is None:
        raise HTTPException(404, "Workspace not found")

    try:
        conversation = get_or_create_conversation(
            db, payload.workspace_id, payload.conversation_id, payload.question
        )
    except ConversationNotFound as exc:
        raise HTTPException(404, str(exc))

    # Read the history BEFORE saving this question, so it isn't included twice.
    history = load_history(db, conversation.id, app_config.CHAT_HISTORY_MESSAGES)
    add_user_message(db, conversation.id, payload.question)
    db.commit()
    conversation_id = conversation.id

    def events() -> Iterator[dict]:
        yield {"type": "meta", "conversation_id": str(conversation_id)}
        yield from stream_answer(
            conversation_id=conversation_id,
            workspace_id=payload.workspace_id,
            question=payload.question,
            history=history,
        )

    return StreamingResponse(
        _sse(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    workspace_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation