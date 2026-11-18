import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.models.chunk import Chunk
from api.models.document_version import DocumentVersion
from api.models.ingestion_job import IngestionJob
from api.schemas.status import JobOut, VersionStatusOut


def get_version_status(db: Session, version_id: uuid.UUID) -> VersionStatusOut | None:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return None

    job = db.scalars(
        select(IngestionJob)
        .where(IngestionJob.document_version_id == version_id)
        .order_by(IngestionJob.attempt.desc())
        .limit(1)
    ).first()

    # count(column) skips NULLs, so this is "chunks that already have a vector".
    total, embedded = db.execute(
        select(func.count(Chunk.id), func.count(Chunk.embedding)).where(
            Chunk.document_version_id == version_id
        )
    ).one()

    return VersionStatusOut(
        version_id=version.id,
        document_id=version.document_id,
        version_number=version.version_number,
        status=version.status,
        error_message=version.error_message,
        attempts=job.attempt if job else 0,
        latest_job=JobOut.model_validate(job) if job else None,
        chunks_total=total,
        chunks_embedded=embedded,
    )