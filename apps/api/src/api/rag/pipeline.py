"""
The RAG flow, free of database and HTTP concerns so it can be tested with fakes:

    question (+ history) -> standalone query -> retrieve -> [no sources? refuse]
                         -> prompt -> stream answer -> validate citations -> Final
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from api.llm.base import LLMError, LLMProvider, Usage
from api.rag.citations import Citation, build_citations
from api.rag.prompts import NO_SOURCES_MESSAGE, build_condense_messages, build_messages
from api.retrieval.types import RetrievedChunk

logger = logging.getLogger(__name__)

CONDENSE_MAX_TOKENS = 1000  # generous: reasoning models spend part of this budget thinking


@dataclass
class Token:
    text: str


@dataclass
class Final:
    answer: str  # cleaned of invalid citation markers; the UI should show this once streaming ends
    citations: list[Citation]
    refused: bool  # True = no reliable, source-backed answer was given
    standalone_query: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


def _standalone_query(question: str, history: list[tuple[str, str]], llm: LLMProvider) -> str:
    """Make a follow-up like "what about 2025?" searchable on its own. Falls back to the raw question."""
    if not history:
        return question
    try:
        rewritten = llm.complete(
            build_condense_messages(question, history), max_tokens=CONDENSE_MAX_TOKENS
        ).text.strip()
        return rewritten or question
    except LLMError as exc:
        logger.warning("Question rewrite failed, using the original question: %s", exc)
        return question


def run_rag(
    question: str,
    history: list[tuple[str, str]],
    *,
    retrieve: Callable[[str], list[RetrievedChunk]],
    llm: LLMProvider,
    max_output_tokens: int,
) -> Iterator[Token | Final]:
    standalone = _standalone_query(question, history, llm)
    sources = retrieve(standalone)

    # Nothing relevant retrieved: refuse WITHOUT calling the model (cheaper, and can't hallucinate).
    if not sources:
        yield Token(NO_SOURCES_MESSAGE)
        yield Final(
            answer=NO_SOURCES_MESSAGE,
            citations=[],
            refused=True,
            standalone_query=standalone,
        )
        return

    messages = build_messages(question, history, sources)
    parts: list[str] = []
    usage = Usage()
    for chunk in llm.stream(messages, max_tokens=max_output_tokens):
        if chunk.text:
            parts.append(chunk.text)
            yield Token(chunk.text)
        if chunk.usage:
            usage = chunk.usage

    citations, answer = build_citations("".join(parts).strip(), sources)
    yield Final(
        answer=answer,
        citations=citations,
        # An answer that cites nothing isn't grounded in the documents: flag it.
        refused=not citations,
        standalone_query=standalone,
        sources=sources,
        usage=usage,
    )