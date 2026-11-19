from dataclasses import dataclass
from uuid import UUID


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    version_number: int
    filename: str
    page_number: int | None
    heading_path: str | None
    content: str
    score: float  # cosine similarity, higher is better