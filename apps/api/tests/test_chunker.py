import pytest

from api.chunking import approx_token_count, chunk_document, get_token_counter
from api.parsers.base import ParsedDocument, ParsedSection


def words(text: str) -> int:
    """Deterministic token counter for tests: one token per whitespace-separated word."""
    return len(text.split())


def doc(*sections: ParsedSection) -> ParsedDocument:
    return ParsedDocument(sections=list(sections))


def chunk(parsed, max_tokens=60, overlap=10):
    return chunk_document(parsed, count_tokens=words, max_tokens=max_tokens, overlap_tokens=overlap)


def test_small_section_is_one_chunk_with_provenance():
    parsed = doc(ParsedSection("Short text here.", page_number=3, heading_path="Policy > Leave"))
    chunks = chunk(parsed)
    assert len(chunks) == 1
    c = chunks[0]
    assert (c.content, c.page_number, c.heading_path, c.index) == (
        "Short text here.", 3, "Policy > Leave", 0
    )
    assert c.metadata["kind"] == "text"


def test_long_text_splits_within_budget_with_overlap_and_loses_nothing():
    paragraphs = [" ".join(f"p{p}w{i}" for i in range(12)) for p in range(20)]  # 20 x 12 words
    chunks = chunk(doc(ParsedSection("\n\n".join(paragraphs))), max_tokens=60, overlap=15)

    assert len(chunks) > 1
    assert all(c.token_count <= 60 for c in chunks)
    joined = "\n\n".join(c.content for c in chunks)
    assert all(p in joined for p in paragraphs)  # nothing dropped
    # overlap: the last paragraph of a chunk reappears at the start of the next one
    for a, b in zip(chunks, chunks[1:]):
        last_para = a.content.split("\n\n")[-1]
        assert b.content.startswith(last_para)


def test_no_overlap_when_disabled():
    paragraphs = [" ".join(f"p{p}w{i}" for i in range(12)) for p in range(10)]
    chunks = chunk(doc(ParsedSection("\n\n".join(paragraphs))), max_tokens=60, overlap=0)
    seen = [p for c in chunks for p in c.content.split("\n\n")]
    assert len(seen) == len(set(seen)) == 10


def test_oversized_paragraph_splits_by_sentence():
    sentences = [" ".join(f"s{s}w{i}" for i in range(15)) + "." for s in range(10)]
    chunks = chunk(doc(ParsedSection(" ".join(sentences))), max_tokens=50, overlap=0)
    assert len(chunks) > 1
    assert all(c.token_count <= 50 for c in chunks)
    # sentences stay whole and are rejoined with spaces, not paragraph breaks
    assert all("\n\n" not in c.content for c in chunks)
    assert chunks[0].content.endswith(".")


def test_giant_unbroken_token_is_hard_split():
    chunks = chunk(doc(ParsedSection("x" * 5000)), max_tokens=100, overlap=0)
    # the word counter sees one "word" per piece <= budget only if pieces contain no spaces:
    # with a words() counter the giant token counts as 1, so it already fits.
    assert len(chunks) == 1
    # with a character-based counter it must be split
    char_counter = lambda t: len(t) // 4
    chunks = chunk_document(
        doc(ParsedSection("x" * 5000)), count_tokens=char_counter, max_tokens=100, overlap_tokens=0
    )
    assert len(chunks) > 1
    assert all(c.token_count <= 100 for c in chunks)
    assert "".join(c.content for c in chunks) == "x" * 5000


def test_heading_path_cost_reduces_the_budget():
    body = "\n\n".join(" ".join(f"a{p}w{i}" for i in range(10)) for p in range(8))
    plain = chunk(doc(ParsedSection(body)), max_tokens=60, overlap=0)
    headed = chunk(
        doc(ParsedSection(body, heading_path="A very long heading path indeed > with many words in it")),
        max_tokens=60,
        overlap=0,
    )
    assert max(c.token_count for c in headed) < max(c.token_count for c in plain)


def test_chunks_never_cross_sections_and_indexes_are_sequential():
    chunks = chunk(
        doc(
            ParsedSection("First section text.", page_number=1, heading_path="A"),
            ParsedSection("Second section text.", page_number=2, heading_path="B"),
        )
    )
    assert [c.index for c in chunks] == [0, 1]
    assert [(c.page_number, c.heading_path) for c in chunks] == [(1, "A"), (2, "B")]
    assert [c.metadata["section_index"] for c in chunks] == [0, 1]


def test_csv_table_rows_keep_ranges_and_no_overlap():
    lines = [f"Row {i}: name: n{i}; dept: HR; city: Lagos; level: {i}" for i in range(1, 31)]
    section = ParsedSection("\n".join(lines), kind="table", metadata={"columns": ["name", "dept"]})
    chunks = chunk(doc(section), max_tokens=60, overlap=10)
    assert len(chunks) > 1
    assert chunks[0].metadata["row_start"] == 1
    assert chunks[-1].metadata["row_end"] == 30
    for a, b in zip(chunks, chunks[1:]):
        assert b.metadata["row_start"] == a.metadata["row_end"] + 1  # contiguous, no overlap


def test_table_without_columns_repeats_header_row():
    lines = ["Tenure | Days | Notes"] + [f"{i} years | {20 + i} | note{i} extra words here" for i in range(30)]
    section = ParsedSection("\n".join(lines), kind="table")
    chunks = chunk(doc(section), max_tokens=60, overlap=0)
    assert len(chunks) > 1
    assert all(c.content.startswith("Tenure | Days | Notes") for c in chunks)
    assert all(c.token_count <= 60 for c in chunks)


def test_fenced_code_not_split_at_blank_lines():
    text = "Intro paragraph.\n\n```python\ndef f():\n    x = 1\n\n    return x\n```\n\nOutro paragraph."
    chunks = chunk(doc(ParsedSection(text)), max_tokens=200, overlap=0)
    assert len(chunks) == 1
    assert "    return x" in chunks[0].content  # blank line inside the fence preserved


def test_invalid_settings_rejected():
    with pytest.raises(ValueError):
        chunk_document(doc(ParsedSection("x")), count_tokens=words, max_tokens=10)
    with pytest.raises(ValueError):
        chunk_document(doc(ParsedSection("x")), count_tokens=words, max_tokens=100, overlap_tokens=60)


def test_token_counters_work():
    assert approx_token_count("") == 0
    assert approx_token_count("abcdefgh") == 2
    counter = get_token_counter()  # tiktoken if available, approximation otherwise
    assert counter("Hello world") >= 1