"""
Quick command-line search, to check that ingestion produced useful vectors.

    docker compose exec api python -m api.scripts.search "how many days of annual leave" \
        --workspace <workspace_id> [--k 5] [--keyword]

Only chunks of READY versions that are the document's CURRENT version are searched, so a
half-processed or superseded version can never appear in results.
"""

import argparse
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.core.database import SessionLocal
from api.embeddings.openai_client import get_embedder
from api.enums.enums import ProcessingStatus
from api.models.chunk import Chunk
from api.models.document import Document
from api.models.document_version import DocumentVersion


def _base_query(workspace_id: uuid.UUID):
    return (
        select(Chunk, Document.filename)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            DocumentVersion.status == ProcessingStatus.READY,
            DocumentVersion.version_number == Document.current_version,
        )
    )


def vector_search(db: Session, workspace_id: uuid.UUID, query: str, k: int):
    query_vector = get_embedder().embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    # pgvector 0.8+: keep scanning the HNSW index until enough rows pass the filters.
    # Harmless if the setting doesn't exist (older pgvector): we just skip it.
    try:
        with db.begin_nested():
            db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    except Exception:  # noqa: BLE001
        pass

    stmt = (
        _base_query(workspace_id)
        .add_columns(distance)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(k)
    )
    return [(chunk, filename, 1 - dist) for chunk, filename, dist in db.execute(stmt)]


def keyword_search(db: Session, workspace_id: uuid.UUID, query: str, k: int):
    ts_query = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.search_vector, ts_query).label("rank")
    stmt = (
        _base_query(workspace_id)
        .add_columns(rank)
        .where(Chunk.search_vector.op("@@")(ts_query))
        .order_by(rank.desc())
        .limit(k)
    )
    return [(chunk, filename, score) for chunk, filename, score in db.execute(stmt)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search ingested chunks")
    parser.add_argument("query")
    parser.add_argument("--workspace", required=True, type=uuid.UUID)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--keyword", action="store_true", help="full-text search instead of vectors")
    args = parser.parse_args()

    with SessionLocal() as db:
        search = keyword_search if args.keyword else vector_search
        results = search(db, args.workspace, args.query, args.k)

    if not results:
        print("No results.")
        return
    label = "rank" if args.keyword else "similarity"
    for position, (chunk, filename, score) in enumerate(results, start=1):
        where = f"p.{chunk.page_number}" if chunk.page_number else "-"
        print(f"\n#{position}  {label}={score:.3f}  {filename}  ({where})")
        if chunk.heading_path:
            print(f"    {chunk.heading_path}")
        print("    " + chunk.content[:300].replace("\n", " ") + ("..." if len(chunk.content) > 300 else ""))


if __name__ == "__main__":
    main()