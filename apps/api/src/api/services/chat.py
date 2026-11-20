"""Conversation persistence and the streaming answer flow used by the chat router."""

import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.core.config import app_config
from api.core.database import SessionLocal
from api.embeddings import EmbeddingError
from api.enums.chat import MessageRole
from api.llm.base import LLMError
from api.llm.factory import get_llm
from api.models.conversation import Conversation
from api.models.message import Message
from api.rag import Final, Token, run_rag
from api.retrieval.search import retrieve

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Something went wrong while answering. Please try again."


class ConversationNotFound(LookupError):
    pass


def get_or_create_conversation(
    db: Session,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    first_question: str,
    user_id: uuid.UUID | None = None,
) -> Conversation:
    if conversation_id is not None:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,  # can't continue another workspace's chat
                Conversation.user_id == user_id,  # ...or another person's
            )
        )
        if conversation is None:
            raise ConversationNotFound("Conversation not found in this workspace")
        return conversation

    conversation = Conversation(
        workspace_id=workspace_id,
        user_id=user_id,
        title=" ".join(first_question.split())[:80],
    )
    db.add(conversation)
    db.flush()
    return conversation


def load_history(db: Session, conversation_id: uuid.UUID, limit: int) -> list[tuple[str, str]]:
    """The last `limit` messages, oldest first, as (role, content) pairs."""
    rows = db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()
    return [(role.value, content) for role, content in reversed(rows)]


def add_user_message(db: Session, conversation_id: uuid.UUID, question: str) -> Message:
    message = Message(conversation_id=conversation_id, role=MessageRole.USER, content=question)
    db.add(message)
    db.flush()
    return message


def _citation_dict(citation) -> dict:
    data = asdict(citation)
    for key in ("chunk_id", "document_id", "version_id"):
        data[key] = str(data[key])
    return data


def stream_answer(
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    question: str,
    history: list[tuple[str, str]],
) -> Iterator[dict]:
    """
    Yields event dicts: {"type": "token"}..., then {"type": "done"} or {"type": "error"}.
    Uses its OWN database session, because it keeps running after the request handler returns.
    """
    started = time.perf_counter()
    llm = get_llm()

    with SessionLocal() as db:

        def retrieve_fn(query):
            try:
                return retrieve(
                    db,
                    workspace_id,
                    query,
                    k=app_config.RETRIEVAL_TOP_K,
                    min_score=app_config.RETRIEVAL_MIN_SCORE,
                )
            finally:
                db.rollback()  # don't hold a transaction open while the model streams

        final: Final | None = None
        try:
            for event in run_rag(
                question,
                history,
                retrieve=retrieve_fn,
                llm=llm,
                max_output_tokens=app_config.LLM_MAX_OUTPUT_TOKENS,
            ):
                if isinstance(event, Token):
                    yield {"type": "token", "text": event.text}
                else:
                    final = event
        except (LLMError, EmbeddingError) as exc:  # messages are user-safe
            logger.warning("Answer failed: %s (cause: %r)", exc, exc.__cause__)
            yield {"type": "error", "message": str(exc)}
            return
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error while answering")
            yield {"type": "error", "message": GENERIC_ERROR_MESSAGE}
            return

        if final is None:
            yield {"type": "error", "message": GENERIC_ERROR_MESSAGE}
            return

        citations = [_citation_dict(c) for c in final.citations]
        message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final.answer,
            citations=citations,
            refused=final.refused,
            model=llm.model,
            prompt_tokens=final.usage.prompt_tokens,
            completion_tokens=final.usage.completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        db.add(message)
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Answered in %d ms (model=%s, sources=%d, cited=%d, refused=%s, tokens=%s/%s)",
            message.latency_ms, llm.model, len(final.sources), len(citations), final.refused,
            final.usage.prompt_tokens, final.usage.completion_tokens,
        )
        yield {
            "type": "done",
            "message_id": str(message.id),
            "conversation_id": str(conversation_id),
            "answer": final.answer,  # authoritative text: replaces the streamed tokens
            "citations": citations,
            "refused": final.refused,
        }