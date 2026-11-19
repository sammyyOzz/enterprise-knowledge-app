import re
from dataclasses import dataclass
from uuid import UUID

from api.retrieval.types import RetrievedChunk

# Matches [1], [12], and grouped forms like [1, 2]. Adjacent ones ([1][3]) match separately.
_MARKER = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
SNIPPET_CHARS = 300


@dataclass
class Citation:
    index: int  # the number the model used, e.g. [2]
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    version_number: int
    filename: str
    page_number: int | None
    heading_path: str | None
    snippet: str
    score: float


def strip_citation_markers(text: str) -> str:
    """Remove [n] markers. Used on past assistant turns, whose numbers refer to old source lists."""
    return re.sub(r"\s*\[\d{1,3}(?:\s*,\s*\d{1,3})*\]", "", text).strip()


def build_citations(answer: str, sources: list[RetrievedChunk]) -> tuple[list[Citation], str]:
    """
    Returns (citations, cleaned_answer). Only sources the answer actually cites are returned,
    in order of first appearance. Markers that point to a source that doesn't exist (the model
    invented a number) are removed from the text rather than shown to the user.
    """
    cited: list[int] = []

    def replace(match: re.Match) -> str:
        numbers = [int(n) for n in re.split(r"\s*,\s*", match.group(1))]
        valid = [n for n in numbers if 1 <= n <= len(sources)]
        for n in valid:
            if n not in cited:
                cited.append(n)
        return f"[{', '.join(str(n) for n in valid)}]" if valid else ""

    cleaned = _MARKER.sub(replace, answer)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)  # tidy gaps left by removed markers
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    citations = []
    for number in cited:
        source = sources[number - 1]
        snippet = source.content[:SNIPPET_CHARS] + ("..." if len(source.content) > SNIPPET_CHARS else "")
        citations.append(
            Citation(
                index=number,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                version_id=source.version_id,
                version_number=source.version_number,
                filename=source.filename,
                page_number=source.page_number,
                heading_path=source.heading_path,
                snippet=snippet,
                score=round(source.score, 4),
            )
        )
    return citations, cleaned