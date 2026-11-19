import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.embeddings.openai_client import get_embedder
from api.enums.enums import ProcessingStatus
from api.models.chunk import Chunk
from api.models.document import Document
from api.models.document_version import DocumentVersion
from api.retrieval.types import RetrievedChunk


def retrieve(
    db: Session,
    workspace_id: uuid.UUID,
    query: str,
    *,
    k: int,
    min_score: float,
) -> list[RetrievedChunk]:
    """
    Vector search restricted to one workspace, READY versions, and each document's CURRENT version.
    Results below `min_score` are dropped: that is what lets the assistant say "I don't know".
    """
    query_vector = get_embedder().embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    # pgvector 0.8+: keep scanning the HNSW index until enough rows pass the filters.
    # Harmless if unsupported (older pgvector): we just skip it.
    try:
        with db.begin_nested():
            db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    except Exception:  # noqa: BLE001
        pass

    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.page_number,
            Chunk.heading_path,
            Document.id.label("document_id"),
            Document.filename,
            DocumentVersion.id.label("version_id"),
            DocumentVersion.version_number,
            distance,
        )
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            DocumentVersion.status == ProcessingStatus.READY,
            DocumentVersion.version_number == Document.current_version,
            Chunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(k)
    )

    results = []
    for row in db.execute(stmt):
        score = 1.0 - float(row.distance)
        if score < min_score:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                version_id=row.version_id,
                version_number=row.version_number,
                filename=row.filename,
                page_number=row.page_number,
                heading_path=row.heading_path,
                content=row.content,
                score=score,
            )
        )
    return results