"""
Celery task that processes one document version.

Pipeline:  download -> PARSE (done) -> CHUNK (done) -> embed (TODO, step 7) -> done
Until embeddings land, a version is marked READY once its chunks are stored, but the chunks
have no vectors yet, so they are not searchable by meaning.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

import api.models  # noqa: F401  (registers all models)
from api.chunking import chunk_document, get_token_counter
from api.core.config import app_config
from api.core.database import SessionLocal
from api.enums.enums import IngestionStage, JobStatus, ProcessingStatus
from api.models.chunk import Chunk
from api.models.ingestion_job import IngestionJob
from api.parsers import ParsingError, parse_document
from api.tasks.celery import celery_app
from api.utils.storage import download_file

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR_MESSAGE = "Processing failed unexpectedly. Please try again or contact support."
MAX_CHUNKS_PER_DOCUMENT = 10_000  # cost/time guard for embedding


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(db, job_id: str, *, user_message: str, detail: str) -> None:
    """
    Record a failure. `detail` (full error text) stays on the job for debugging;
    `user_message` goes on the version, which the API exposes, so it must be safe to show.
    """
    db.rollback()
    job = db.get(IngestionJob, uuid.UUID(job_id))
    job.status = JobStatus.FAILED
    job.finished_at = _now()
    job.error_message = detail[:2000]
    job.document_version.status = ProcessingStatus.FAILED
    job.document_version.error_message = user_message[:2000]
    db.commit()


# soft limit raises inside the task (so it's recorded as FAILED); the hard limit
# is the backstop that kills a hung worker process.
@celery_app.task(
    name="ingestion.process_document_version", soft_time_limit=840, time_limit=900
)
def process_document_version(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(IngestionJob, uuid.UUID(job_id))
        if job is None:
            logger.error("Ingestion job %s not found", job_id)
            return

        # Celery may re-deliver a task if a worker died (acks_late). Don't redo finished work.
        if job.status == JobStatus.SUCCEEDED:
            logger.info("Job %s already succeeded, skipping", job_id)
            return

        version = job.document_version
        # Read what we need now, so no database transaction stays open while we work.
        filename = version.document.filename
        workspace_id = version.document.workspace_id
        storage_key = version.storage_key

        job.status = JobStatus.RUNNING
        job.stage = IngestionStage.PARSING
        job.started_at = _now()
        job.error_message = None
        version.status = ProcessingStatus.PROCESSING
        db.commit()

        try:
            # ---- 1. parse ----------------------------------------------------
            raw = download_file(storage_key)
            parsed = parse_document(filename, raw)
            version.page_count = parsed.page_count
            job.stage = IngestionStage.CHUNKING
            db.commit()

            # ---- 2. chunk ----------------------------------------------------
            chunks = chunk_document(
                parsed,
                count_tokens=get_token_counter(),
                max_tokens=app_config.CHUNK_MAX_TOKENS,
                overlap_tokens=app_config.CHUNK_OVERLAP_TOKENS,
            )
            if not chunks:
                raise ParsingError("Document has no content to index")
            if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
                raise ParsingError(
                    f"Document is too large to index ({len(chunks):,} chunks; "
                    f"the limit is {MAX_CHUNKS_PER_DOCUMENT:,})"
                )
            logger.info(
                "Job %s: %s -> %d sections, %d chunks (avg %d tokens, max %d)",
                job_id, filename, len(parsed.sections), len(chunks),
                sum(c.token_count for c in chunks) // len(chunks),
                max(c.token_count for c in chunks),
            )

            # Replace this version's chunks in ONE transaction, so a retry or re-delivery
            # can never leave duplicate or half-written chunks behind.
            db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
            db.add_all(
                Chunk(
                    document_version_id=version.id,
                    workspace_id=workspace_id,
                    chunk_index=c.index,
                    content=c.content,
                    token_count=c.token_count,
                    page_number=c.page_number,
                    heading_path=c.heading_path,
                    meta=c.metadata,
                )
                for c in chunks
            )
            job.stage = IngestionStage.EMBEDDING
            db.commit()

            # ---- 3. embed ----------------------------------------------------
            # TODO (step 7): embed each chunk (heading_path + "\n\n" + content), store vectors.

            job.stage = IngestionStage.DONE
            job.status = JobStatus.SUCCEEDED
            job.finished_at = _now()
            version.status = ProcessingStatus.READY
            db.commit()

        except ParsingError as exc:
            # Deterministic: retrying the same file will fail the same way. No re-raise.
            logger.warning("Job %s: %s", job_id, exc)
            _fail(db, job_id, user_message=str(exc), detail=str(exc))

        except Exception as exc:  # noqa: BLE001  (includes SoftTimeLimitExceeded)
            logger.exception("Job %s failed", job_id)
            _fail(
                db,
                job_id,
                user_message=UNEXPECTED_ERROR_MESSAGE,
                detail=f"{type(exc).__name__}: {exc}",
            )
            raise