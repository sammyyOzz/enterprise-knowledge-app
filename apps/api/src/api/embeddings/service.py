"""
Embedding generation: token-aware batching, error mapping, dimension checks.

Pure logic: nothing here imports api.core.config, so it can be unit-tested with a fake client.
The OpenAI SDK already retries 429/5xx/connection errors with exponential backoff (set via
`max_retries` when the client is built); this layer turns whatever still fails into
user-safe errors.
"""

import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import openai

logger = logging.getLogger(__name__)

MAX_INPUT_TOKENS = 8000  # API limit is 8191 per input
MAX_BATCH_ITEMS = 256  # API limit is 2048 inputs per request
MAX_BATCH_TOKENS = 100_000  # API limit is 300k tokens per request


class EmbeddingError(Exception):
    """Embedding failed. The message is written to be safe to show to users."""


class EmbeddingUnavailable(EmbeddingError):
    """Transient failure (rate limit, timeout, outage). Retrying later should work."""


@dataclass
class EmbeddedBatch:
    offset: int  # index of the first text of this batch in the original list
    vectors: list[list[float]]
    tokens: int  # tokens billed for this batch


def build_embedding_text(heading_path: str | None, content: str) -> str:
    """
    What actually gets embedded. Prefixing the heading path gives short or ambiguous chunks
    their context ("Leave Policy > Annual Leave" + "20 days per year").
    """
    return f"{heading_path}\n\n{content}" if heading_path else content


def plan_batches(
    token_counts: Sequence[int],
    max_items: int = MAX_BATCH_ITEMS,
    max_tokens: int = MAX_BATCH_TOKENS,
) -> list[range]:
    """Group consecutive texts into batches within both the item and token limits."""
    batches: list[range] = []
    start = items = tokens = 0
    for index, count in enumerate(token_counts):
        if items and (items >= max_items or tokens + count > max_tokens):
            batches.append(range(start, index))
            start, items, tokens = index, 0, 0
        items += 1
        tokens += count
    if items:
        batches.append(range(start, len(token_counts)))
    return batches


class Embedder:
    def __init__(
        self,
        client: Any,  # openai.OpenAI (or a fake with the same .embeddings.create interface)
        *,
        model: str,
        dimensions: int,
        count_tokens: Callable[[str], int],
        max_batch_items: int = MAX_BATCH_ITEMS,
        max_batch_tokens: int = MAX_BATCH_TOKENS,
    ) -> None:
        self.client = client
        self.model = model
        self.dimensions = dimensions
        self.count_tokens = count_tokens
        self.max_batch_items = max_batch_items
        self.max_batch_tokens = max_batch_tokens

    # ------------------------------------------------------------------ #
    def iter_embeddings(self, texts: Sequence[str]) -> Iterator[EmbeddedBatch]:
        """Yield one EmbeddedBatch per API call, so callers can persist progress as they go."""
        prepared = [self._prepare(text) for text in texts]
        inputs = [text for text, _ in prepared]
        counts = [tokens for _, tokens in prepared]
        for batch in plan_batches(counts, self.max_batch_items, self.max_batch_tokens):
            vectors, billed = self._request(
                [inputs[i] for i in batch], fallback_tokens=sum(counts[i] for i in batch)
            )
            yield EmbeddedBatch(offset=batch.start, vectors=vectors, tokens=billed)

    def embed_query(self, text: str) -> list[float]:
        vectors, _ = self._request([self._prepare(text)[0]], fallback_tokens=0)
        return vectors[0]

    # ------------------------------------------------------------------ #
    def _prepare(self, text: str) -> tuple[str, int]:
        """Guard against inputs over the API limit by truncating (should be rare: chunks are ~600 tokens)."""
        tokens = self.count_tokens(text)
        if tokens > MAX_INPUT_TOKENS:
            logger.warning("Truncating an embedding input of %d tokens", tokens)
            text = text[: int(len(text) * MAX_INPUT_TOKENS / tokens * 0.95)]
            tokens = self.count_tokens(text)
        return text, tokens

    def _request(self, batch: list[str], *, fallback_tokens: int) -> tuple[list[list[float]], int]:
        kwargs: dict[str, Any] = {}
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = self.dimensions  # only the v3 models accept this

        try:
            response = self.client.embeddings.create(model=self.model, input=batch, **kwargs)
        except openai.RateLimitError as exc:
            if getattr(exc, "code", None) == "insufficient_quota":
                raise EmbeddingError("The embedding service quota has been exceeded.") from exc
            raise EmbeddingUnavailable(
                "The embedding service is busy. Please retry in a few minutes."
            ) from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:  # incl. timeouts
            raise EmbeddingUnavailable(
                "The embedding service is temporarily unavailable. Please retry in a few minutes."
            ) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise EmbeddingError("The embedding service is not configured correctly.") from exc
        except openai.APIError as exc:
            raise EmbeddingError("The embedding service rejected the request.") from exc

        data = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in data]
        if len(vectors) != len(batch):
            raise EmbeddingError("The embedding service returned an unexpected response.")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingError(
                f"Embedding size mismatch: expected {self.dimensions} dimensions, "
                f"got {len(vectors[0])}. Check EMBEDDING_MODEL and EMBEDDING_DIM."
            )
        usage = getattr(getattr(response, "usage", None), "total_tokens", None)
        return vectors, usage or fallback_tokens