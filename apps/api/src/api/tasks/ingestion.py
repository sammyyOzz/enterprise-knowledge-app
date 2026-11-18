"""
Celery task that processes one document version.

Pipeline:  download -> parse -> chunk -> embed -> done

A version only becomes READY after EVERY chunk has its vector, so search never sees a
half-embedded document. Chunk rows are written before embedding and vectors are saved batch
by batch (so progress survives and memory stays small). If anything fails, the version is
FAILED and a retry starts from scratch, replacing all of that version's chunks.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, update

import api.models  # noqa: F401  (registers all models)
from api.chunking import chunk_document, get_token_counter
from api.core.config import app_config
from api.core.database import SessionLocal
from api.embeddings import EmbeddingError, EmbeddingUnavailable, build_embedding_text
from api.embeddings.openai_client import get_embedder
from api.enums.enums import IngestionStage, JobStatus, ProcessingStatus
from api.models.chunk import Chunk
from api.models.ingestion_job import IngestionJob
from api.parsers import ParsingError, parse_document
from api.tasks.celery import celery_app
from api.utils.storage import download_file

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR_MESSAGE = "Processing failed unexpectedly. Please try again or contact support."


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

        version = job.document_version
        # Read what we need now, so no database transaction stays open while we work.
        filename = version.document.filename
        workspace_id = version.document.workspace_id
        storage_key = version.storage_key

        # Atomically claim the job: only a QUEUED job may start. This stops duplicate or
        # re-delivered messages from running the same job twice, and stops a job that already
        # finished (or was failed by the reaper in tasks/maintenance.py) from being resurrected.
        claimed = db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id, IngestionJob.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.RUNNING,
                stage=IngestionStage.PARSING,
                started_at=_now(),
                error_message=None,
            )
        ).rowcount
        db.commit()
        if not claimed:
            logger.info("Job %s is no longer queued (already started, finished or reaped); skipping", job_id)
            return
        db.refresh(job)
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
            if len(chunks) > app_config.MAX_CHUNKS_PER_DOCUMENT:
                raise ParsingError(
                    f"Document is too large to index ({len(chunks):,} chunks; "
                    f"the limit is {app_config.MAX_CHUNKS_PER_DOCUMENT:,})"
                )
            logger.info(
                "Job %s: %s -> %d sections, %d chunks (avg %d tokens, max %d)",
                job_id, filename, len(parsed.sections), len(chunks),
                sum(c.token_count for c in chunks) // len(chunks),
                max(c.token_count for c in chunks),
            )

            # Replace this version's chunks in ONE transaction, so a retry or re-delivery
            # can never leave duplicate or half-written chunks behind.
            chunk_ids = [uuid.uuid4() for _ in chunks]
            db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
            db.add_all(
                Chunk(
                    id=chunk_id,
                    document_version_id=version.id,
                    workspace_id=workspace_id,
                    chunk_index=c.index,
                    content=c.content,
                    token_count=c.token_count,
                    page_number=c.page_number,
                    heading_path=c.heading_path,
                    meta=c.metadata,
                )
                for chunk_id, c in zip(chunk_ids, chunks)
            )
            job.stage = IngestionStage.EMBEDDING
            db.commit()

            # ---- 3. embed ----------------------------------------------------
            embedder = get_embedder()
            texts = [build_embedding_text(c.heading_path, c.content) for c in chunks]
            total_tokens = 0
            for batch in embedder.iter_embeddings(texts):
                db.execute(
                    update(Chunk),
                    [
                        {
                            "id": chunk_ids[batch.offset + i],
                            "embedding": vector,
                            "embedding_model": embedder.model,
                        }
                        for i, vector in enumerate(batch.vectors)
                    ],
                )
                total_tokens += batch.tokens
                job.updated_at = _now()  # heartbeat: shows the job is alive (see retry's stale check)
                db.commit()
            logger.info(
                "Job %s: embedded %d chunks with %s (%d tokens billed)",
                job_id, len(chunks), embedder.model, total_tokens,
            )

            # ---- 4. done -----------------------------------------------------
            job.stage = IngestionStage.DONE
            job.status = JobStatus.SUCCEEDED
            job.finished_at = _now()
            version.status = ProcessingStatus.READY
            db.commit()

        except ParsingError as exc:
            # Deterministic: retrying the same file will fail the same way. No re-raise.
            logger.warning("Job %s: %s", job_id, exc)
            _fail(db, job_id, user_message=str(exc), detail=str(exc))

        except EmbeddingError as exc:
            # EmbeddingUnavailable is transient (retry later); other EmbeddingErrors are
            # configuration/quota problems. Either way the message is user-safe.
            level = logging.WARNING if isinstance(exc, EmbeddingUnavailable) else logging.ERROR
            logger.log(level, "Job %s: embedding failed: %s (cause: %r)", job_id, exc, exc.__cause__)
            _fail(db, job_id, user_message=str(exc), detail=f"{exc} | cause: {exc.__cause__!r}")

        except Exception as exc:  # noqa: BLE001  (includes SoftTimeLimitExceeded)
            logger.exception("Job %s failed", job_id)
            _fail(
                db,
                job_id,
                user_message=UNEXPECTED_ERROR_MESSAGE,
                detail=f"{type(exc).__name__}: {exc}",
            )
            raise