import logging
import math
from collections.abc import Callable
from functools import lru_cache

logger = logging.getLogger(__name__)

TokenCounter = Callable[[str], int]


def approx_token_count(text: str) -> int:
    """Rough fallback: ~4 characters per token for English text."""
    return math.ceil(len(text) / 4) if text else 0


@lru_cache(maxsize=4)
def get_token_counter(encoding_name: str = "cl100k_base") -> TokenCounter:
    """
    Exact counts via tiktoken (cl100k_base is the tokenizer used by OpenAI's
    text-embedding-3 models). tiktoken downloads its vocabulary on first use; if that
    fails (offline, read-only cache dir) we fall back to an approximation and log a warning,
    so ingestion keeps working with slightly less precise chunk sizes.
    """
    try:
        import tiktoken

        encoding = tiktoken.get_encoding(encoding_name)

        def count(text: str) -> int:
            # disallowed_special=() so text that merely *contains* "<|endoftext|>" doesn't raise
            return len(encoding.encode(text, disallowed_special=()))

        return count
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tiktoken unavailable (%s); using approximate token counts. "
            "Set TIKTOKEN_CACHE_DIR to a writable directory to fix this.",
            exc,
        )
        return approx_token_count