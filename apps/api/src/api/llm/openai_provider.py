from collections.abc import Iterator
from typing import Any

import openai

from api.llm.base import (
    Completion,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMUnavailable,
    StreamChunk,
    Usage,
)


def _translate(exc: openai.OpenAIError) -> LLMError:
    """Map SDK errors to user-safe ones. The original stays attached as __cause__ for logs."""
    if isinstance(exc, openai.RateLimitError):
        if getattr(exc, "code", None) == "insufficient_quota":
            return LLMError("The language model quota has been exceeded.")
        return LLMUnavailable("The language model is busy. Please try again in a moment.")
    if isinstance(exc, (openai.APIConnectionError, openai.InternalServerError)):  # incl. timeouts
        return LLMUnavailable("The language model is temporarily unavailable. Please try again shortly.")
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMError("The language model is not configured correctly.")
    if isinstance(exc, openai.APIError):
        return LLMError("The language model rejected the request.")
    return LLMError("The language model request failed.")


class OpenAIProvider(LLMProvider):
    """
    Chat Completions API. Deliberately sends no `temperature`/`top_p`: current OpenAI reasoning
    models reject them. `reasoning_effort` is only sent when you configure it.
    """

    name = "openai"

    def __init__(self, client: Any, *, model: str, reasoning_effort: str | None = None) -> None:
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def _kwargs(self, messages: list[LLMMessage], max_tokens: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_completion_tokens": max_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    def complete(self, messages: list[LLMMessage], *, max_tokens: int) -> Completion:
        try:
            response = self.client.chat.completions.create(**self._kwargs(messages, max_tokens))
        except openai.OpenAIError as exc:
            raise _translate(exc) from exc

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("The language model returned an empty response.")
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            usage=Usage(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
            ),
        )

    def stream(self, messages: list[LLMMessage], *, max_tokens: int) -> Iterator[StreamChunk]:
        produced = False
        try:
            stream = self.client.chat.completions.create(
                **self._kwargs(messages, max_tokens),
                stream=True,
                stream_options={"include_usage": True},
            )
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        produced = True
                        yield StreamChunk(text=delta)
                usage = getattr(chunk, "usage", None)
                if usage:
                    yield StreamChunk(
                        usage=Usage(
                            prompt_tokens=getattr(usage, "prompt_tokens", None),
                            completion_tokens=getattr(usage, "completion_tokens", None),
                        )
                    )
        except openai.OpenAIError as exc:
            raise _translate(exc) from exc

        if not produced:
            # Reasoning models can spend the whole output budget thinking and emit no text.
            raise LLMError("The language model returned an empty response.")