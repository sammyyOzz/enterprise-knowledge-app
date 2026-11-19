"""
Provider-neutral LLM interface. The RAG pipeline only ever talks to LLMProvider, so switching
providers means writing one new subclass and registering it in llm/factory.py.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class StreamChunk:
    """Either a piece of text, or (once, at the end) token usage."""

    text: str = ""
    usage: Usage | None = None


@dataclass
class Completion:
    text: str
    usage: Usage = field(default_factory=Usage)


class LLMError(Exception):
    """The model call failed. The message is written to be safe to show to users."""


class LLMUnavailable(LLMError):
    """Transient failure (rate limit, timeout, outage). Trying again shortly should work."""


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def complete(self, messages: list[LLMMessage], *, max_tokens: int) -> Completion:
        """One non-streaming call. Used for short helper tasks (e.g. rewriting a question)."""

    @abstractmethod
    def stream(self, messages: list[LLMMessage], *, max_tokens: int) -> Iterator[StreamChunk]:
        """Yield text chunks as they arrive, then one final chunk carrying token usage."""