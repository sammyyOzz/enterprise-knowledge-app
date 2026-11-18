# Deliberately does NOT import openai_client (which needs app config), so this package
# stays importable in unit tests. Import `get_embedder` from api.embeddings.openai_client.
from api.embeddings.service import (
    EmbeddedBatch,
    Embedder,
    EmbeddingError,
    EmbeddingUnavailable,
    build_embedding_text,
    plan_batches,
)

__all__ = [
    "EmbeddedBatch",
    "Embedder",
    "EmbeddingError",
    "EmbeddingUnavailable",
    "build_embedding_text",
    "plan_batches",
]