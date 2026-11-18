from functools import lru_cache

from openai import OpenAI

from api.chunking import get_token_counter
from api.core.config import app_config
from api.embeddings.service import Embedder


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """One shared Embedder per process (the OpenAI client is thread-safe and pools connections)."""
    client = OpenAI(
        api_key=app_config.OPENAI_API_KEY,
        max_retries=5,  # SDK backs off exponentially on 429 / 5xx / connection errors
        timeout=60,
    )
    return Embedder(
        client,
        model=app_config.EMBEDDING_MODEL,
        dimensions=app_config.EMBEDDING_DIM,
        count_tokens=get_token_counter(),
    )