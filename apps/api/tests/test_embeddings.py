from types import SimpleNamespace

import httpx
import openai
import pytest

from api.embeddings import (
    Embedder,
    EmbeddingError,
    EmbeddingUnavailable,
    build_embedding_text,
    plan_batches,
)

DIM = 8


def words(text: str) -> int:
    return len(text.split())


class FakeEmbeddings:
    """Mimics client.embeddings.create; returns data in REVERSED order to test re-sorting."""

    def __init__(self, dim=DIM, error=None):
        self.dim, self.error, self.calls = dim, error, []

    def create(self, *, model, input, **kwargs):
        self.calls.append({"model": model, "input": list(input), "kwargs": kwargs})
        if self.error:
            raise self.error
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text.split()))] + [0.0] * (self.dim - 1))
            for i, text in enumerate(input)
        ]
        return SimpleNamespace(
            data=list(reversed(data)),
            usage=SimpleNamespace(total_tokens=sum(len(t.split()) for t in input)),
        )


def make_embedder(client, **kwargs):
    return Embedder(
        SimpleNamespace(embeddings=client),
        model=kwargs.pop("model", "text-embedding-3-small"),
        dimensions=DIM,
        count_tokens=words,
        **kwargs,
    )


def http_error(cls, status, **extra):
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None, **extra)


# ----------------------------- helpers ----------------------------- #
def test_build_embedding_text_prefixes_heading():
    assert build_embedding_text("Leave > Annual", "20 days") == "Leave > Annual\n\n20 days"
    assert build_embedding_text(None, "20 days") == "20 days"


def test_plan_batches_respects_item_and_token_limits():
    assert plan_batches([1] * 5, max_items=2, max_tokens=100) == [range(0, 2), range(2, 4), range(4, 5)]
    assert plan_batches([40, 40, 40, 40], max_items=100, max_tokens=100) == [range(0, 2), range(2, 4)]
    # a single oversized item still gets its own batch instead of being dropped
    assert plan_batches([500, 10], max_items=100, max_tokens=100) == [range(0, 1), range(1, 2)]
    assert plan_batches([], max_items=2, max_tokens=100) == []


# ----------------------------- embedder ----------------------------- #
def test_batches_keep_order_and_offsets_and_report_tokens():
    fake = FakeEmbeddings()
    embedder = make_embedder(fake, max_batch_items=2)
    texts = ["a", "b b", "c c c", "d d d d", "e"]
    batches = list(embedder.iter_embeddings(texts))

    assert [b.offset for b in batches] == [0, 2, 4]
    flat = [v[0] for b in batches for v in b.vectors]
    assert flat == [1.0, 2.0, 3.0, 4.0, 1.0]  # matches input order despite reversed API data
    assert sum(b.tokens for b in batches) == 1 + 2 + 3 + 4 + 1
    assert len(fake.calls) == 3


def test_dimensions_sent_only_for_v3_models():
    fake = FakeEmbeddings()
    list(make_embedder(fake).iter_embeddings(["x"]))
    assert fake.calls[0]["kwargs"] == {"dimensions": DIM}

    fake = FakeEmbeddings()
    list(make_embedder(fake, model="text-embedding-ada-002").iter_embeddings(["x"]))
    assert fake.calls[0]["kwargs"] == {}


def test_embed_query_returns_single_vector():
    vector = make_embedder(FakeEmbeddings()).embed_query("hello there")
    assert len(vector) == DIM and vector[0] == 2.0


def test_dimension_mismatch_is_an_error():
    embedder = make_embedder(FakeEmbeddings(dim=4))
    with pytest.raises(EmbeddingError, match="size mismatch"):
        list(embedder.iter_embeddings(["x"]))


def test_oversized_input_is_truncated_not_rejected():
    fake = FakeEmbeddings()
    huge = "word " * 20_000
    list(make_embedder(fake).iter_embeddings([huge]))
    sent = fake.calls[0]["input"][0]
    assert len(sent.split()) <= 8000


# ----------------------------- error mapping ----------------------------- #
def test_rate_limit_is_transient():
    embedder = make_embedder(FakeEmbeddings(error=http_error(openai.RateLimitError, 429)))
    with pytest.raises(EmbeddingUnavailable):
        list(embedder.iter_embeddings(["x"]))


def test_quota_exhaustion_is_not_transient():
    error = http_error(openai.RateLimitError, 429)
    error.code = "insufficient_quota"
    embedder = make_embedder(FakeEmbeddings(error=error))
    with pytest.raises(EmbeddingError, match="quota") as info:
        list(embedder.iter_embeddings(["x"]))
    assert not isinstance(info.value, EmbeddingUnavailable)


def test_server_error_and_connection_error_are_transient():
    for error in (
        http_error(openai.InternalServerError, 500),
        openai.APIConnectionError(request=httpx.Request("POST", "https://x")),
    ):
        with pytest.raises(EmbeddingUnavailable):
            list(make_embedder(FakeEmbeddings(error=error)).iter_embeddings(["x"]))


def test_auth_error_is_a_configuration_error_without_leaking_details():
    embedder = make_embedder(FakeEmbeddings(error=http_error(openai.AuthenticationError, 401)))
    with pytest.raises(EmbeddingError, match="not configured") as info:
        list(embedder.iter_embeddings(["x"]))
    assert "boom" not in str(info.value)  # the raw provider message is not exposed
    assert info.value.__cause__ is not None  # but it is kept for logs