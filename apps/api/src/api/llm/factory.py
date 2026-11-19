"""
Chooses the LLM provider from config (LLM_PROVIDER).

To add a provider (Anthropic, Groq, a local model, ...):
  1. subclass LLMProvider in api/llm/<name>_provider.py (implement complete + stream)
  2. write a small builder function below and add it to PROVIDERS
  3. set LLM_PROVIDER=<name> and LLM_MODEL=<model id> in your environment
Nothing else in the app changes.
"""

from collections.abc import Callable
from functools import lru_cache

from openai import OpenAI

from api.core.config import app_config
from api.llm.base import LLMProvider
from api.llm.openai_provider import OpenAIProvider


def _build_openai() -> LLMProvider:
    client = OpenAI(
        api_key=app_config.OPENAI_API_KEY,
        max_retries=3,  # SDK backs off on 429 / 5xx / connection errors
        timeout=60,
    )
    return OpenAIProvider(
        client, model=app_config.LLM_MODEL, reasoning_effort=app_config.LLM_REASONING_EFFORT
    )


PROVIDERS: dict[str, Callable[[], LLMProvider]] = {
    "openai": _build_openai,
}


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    name = app_config.LLM_PROVIDER.strip().lower()
    builder = PROVIDERS.get(name)
    if builder is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{app_config.LLM_PROVIDER}'. Available: {', '.join(sorted(PROVIDERS))}"
        )
    return builder()