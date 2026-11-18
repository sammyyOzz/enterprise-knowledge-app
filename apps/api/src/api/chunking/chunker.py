"""
Turns a ParsedDocument into chunks sized for embedding.

Rules
-----
* A chunk never crosses a section boundary, so every chunk has exactly one page number and
  one heading path (needed for accurate citations).
* Text sections are packed paragraph by paragraph up to `max_tokens`. Paragraphs that are too
  big are split by line, then sentence, and as a last resort by words/characters.
* Consecutive chunks of the same section overlap by up to `overlap_tokens` (whole units only),
  so a fact on a boundary appears intact in at least one chunk.
* Table sections are packed row by row with no overlap. Tables without column metadata
  (e.g. from DOCX) repeat their first row (the header) at the top of every chunk.
* The heading path is embedded together with the chunk later, so its token cost is
  reserved out of the budget up front.
* Fenced code blocks are never split at blank lines.
"""

import re
from dataclasses import dataclass, field

from api.chunking.tokens import TokenCounter
from api.parsers.base import ParsedDocument, ParsedSection

JOINER_COST = 1  # approximate tokens spent on the whitespace between two units
_ROW = re.compile(r"^Row (\d+):")
_FENCE = re.compile(r"^(```+|~~~+)")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")


@dataclass
class ChunkData:
    index: int
    content: str
    token_count: int  # tokens in `content` alone (the heading prefix is added at embed time)
    page_number: int | None
    heading_path: str | None
    metadata: dict = field(default_factory=dict)


@dataclass
class _Unit:
    text: str
    tokens: int
    joiner: str  # whitespace placed BEFORE this unit when it follows another one


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def chunk_document(
    parsed: ParsedDocument,
    *,
    count_tokens: TokenCounter,
    max_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[ChunkData]:
    if max_tokens < 50:
        raise ValueError("max_tokens must be at least 50")
    if not 0 <= overlap_tokens < max_tokens // 2:
        raise ValueError("overlap_tokens must be >= 0 and less than half of max_tokens")

    chunks: list[ChunkData] = []
    for section_index, section in enumerate(parsed.sections):
        for content, metadata in _chunk_section(
            section, count_tokens, max_tokens, overlap_tokens
        ):
            metadata = {"kind": section.kind, "section_index": section_index, **metadata}
            chunks.append(
                ChunkData(
                    index=len(chunks),
                    content=content,
                    token_count=count_tokens(content),
                    page_number=section.page_number,
                    heading_path=section.heading_path,
                    metadata=metadata,
                )
            )
    return chunks


# --------------------------------------------------------------------------- #
# Per-section chunking
# --------------------------------------------------------------------------- #
def _chunk_section(
    section: ParsedSection, count: TokenCounter, max_tokens: int, overlap_tokens: int
) -> list[tuple[str, dict]]:
    prefix_cost = (count(section.heading_path) + JOINER_COST) if section.heading_path else 0
    budget = max(max_tokens // 2, max_tokens - prefix_cost)

    is_table = section.kind == "table"
    if is_table:
        units = _table_units(section.text, budget, count)
        overlap = 0
    else:
        units = _text_units(section.text, budget, count)
        overlap = overlap_tokens
    if not units:
        return []

    header: _Unit | None = None
    if is_table and not section.metadata.get("columns") and len(units) > 1:
        header, units = units[0], units[1:]
        budget = max(1, budget - header.tokens - JOINER_COST)

    results = []
    for group in _pack(units, budget, overlap):
        metadata: dict = {}
        if is_table:
            rows = [int(m.group(1)) for u in group if (m := _ROW.match(u.text))]
            if rows:
                metadata = {"row_start": min(rows), "row_end": max(rows)}
        rendered = _render(([header] if header else []) + group)
        if rendered.strip():
            results.append((rendered, metadata))
    return results


def _render(units: list[_Unit]) -> str:
    text = units[0].text
    for unit in units[1:]:
        text += unit.joiner + unit.text
    return text


# --------------------------------------------------------------------------- #
# Splitting text into units
# --------------------------------------------------------------------------- #
def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines, but never inside a fenced code block."""
    paragraphs: list[str] = []
    current: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        match = _FENCE.match(stripped)
        if match:
            marker = match.group(1)[:3]
            if fence is None:
                fence = marker
            elif stripped.startswith(fence):
                fence = None
        if not stripped and fence is None:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [p for p in paragraphs if p]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s and s.strip()]


def _split_by_chars(text: str, budget: int, count: TokenCounter) -> list[str]:
    """Last resort for text with no usable break points (CJK without punctuation, base64, ...)."""
    if count(text) <= budget or len(text) <= 1:
        return [text]
    step = max(1, int(len(text) * budget / max(count(text), 1) * 0.9))
    pieces = [text[i : i + step] for i in range(0, len(text), step)]
    out: list[str] = []
    for piece in pieces:
        out.extend([piece] if count(piece) <= budget else _split_by_chars(piece, budget, count))
    return out


def _fit(text: str, budget: int, count: TokenCounter) -> list[str]:
    """Return `text` as pieces that each fit the budget, preferring to break at spaces."""
    if count(text) <= budget:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    for word in text.split(" "):
        candidate = " ".join(current + [word])
        if count(candidate) <= budget:
            current.append(word)
            continue
        if current:
            pieces.append(" ".join(current))
            current = []
        if count(word) > budget:
            pieces.extend(_split_by_chars(word, budget, count))
        else:
            current = [word]
    if current:
        pieces.append(" ".join(current))
    return pieces


def _text_units(text: str, budget: int, count: TokenCounter) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in _split_paragraphs(text):
        tokens = count(paragraph)
        if tokens <= budget:
            units.append(_Unit(paragraph, tokens, "\n\n"))
            continue

        # Oversized paragraph: split by line, then sentence, then words/characters.
        parts: list[tuple[str, str]] = []
        for line in paragraph.split("\n"):
            line = line.rstrip()  # rstrip only: keeps indentation (lists, code)
            if not line.strip():
                continue
            if count(line) <= budget:
                parts.append((line, "\n"))
                continue
            for s_index, sentence in enumerate(_split_sentences(line)):
                for p_index, piece in enumerate(_fit(sentence, budget, count)):
                    parts.append((piece, "\n" if (s_index == 0 and p_index == 0) else " "))
        if parts:
            parts[0] = (parts[0][0], "\n\n")  # the paragraph itself starts a new block
        units.extend(_Unit(t, count(t), joiner) for t, joiner in parts)
    return units


def _table_units(text: str, budget: int, count: TokenCounter) -> list[_Unit]:
    units: list[_Unit] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for index, piece in enumerate(_fit(line, budget, count)):
            units.append(_Unit(piece, count(piece), "\n" if index == 0 else " "))
    return units


# --------------------------------------------------------------------------- #
# Packing units into chunks
# --------------------------------------------------------------------------- #
def _group_tokens(group: list[_Unit]) -> int:
    return sum(u.tokens for u in group) + JOINER_COST * max(len(group) - 1, 0)


def _overlap_tail(group: list[_Unit], overlap: int) -> list[_Unit]:
    if overlap <= 0:
        return []
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(group):
        cost = unit.tokens + (JOINER_COST if tail else 0)
        if total + cost > overlap:
            break
        tail.insert(0, unit)
        total += cost
    return tail


def _pack(units: list[_Unit], budget: int, overlap: int) -> list[list[_Unit]]:
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    used = 0
    for unit in units:
        cost = unit.tokens + (JOINER_COST if current else 0)
        if current and used + cost > budget:
            groups.append(current)
            current = _overlap_tail(current, overlap)
            used = _group_tokens(current)
            if current and used + unit.tokens + JOINER_COST > budget:
                current, used = [], 0  # overlap doesn't fit alongside the next unit: drop it
            cost = unit.tokens + (JOINER_COST if current else 0)
        current.append(unit)
        used += cost
    if current:
        groups.append(current)
    return groups