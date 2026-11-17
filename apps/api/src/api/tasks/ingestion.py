"""
Celery task that processes one document version.

Right now this is a STUB: it proves the pipeline is wired end to end
(API -> DB -> queue -> worker -> object storage -> DB status updates).
Steps 5-7 (parsing, chunking, embedding) replace the marked section below.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

import api.models  # noqa: F401  (registers all models)
from api.core.database import SessionLocal
from api.enums.enums import IngestionStage, JobStatus, ProcessingStatus
from api.models.chunk import Chunk
from api.models.ingestion_job import IngestionJob
from api.tasks.celery import celery_app
from api.utils.storage import download_file

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        job.status = JobStatus.RUNNING
        job.stage = IngestionStage.PARSING
        job.started_at = _now()
        job.error_message = None
        version.status = ProcessingStatus.PROCESSING
        db.commit()

        try:
            # Idempotency: a retry or re-delivery must not leave duplicate chunks behind.
            db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))

            raw = download_file(version.storage_key)
            logger.info(
                "Job %s: downloaded %s (%d bytes)", job_id, version.storage_key, len(raw)
            )

            # ----------------------------------------------------------------
            # TODO (steps 5-7): replace this block with the real pipeline
            #   1. parse `raw` into text + page/section metadata
            #   2. chunk the text, insert Chunk rows
            #   3. embed the chunks, store vectors
            # Update job.stage and commit between stages.
            # ----------------------------------------------------------------

            job.stage = IngestionStage.DONE
            job.status = JobStatus.SUCCEEDED
            job.finished_at = _now()
            version.status = ProcessingStatus.READY
            db.commit()

        except Exception as exc:  # noqa: BLE001  (includes SoftTimeLimitExceeded)
            logger.exception("Job %s failed", job_id)
            db.rollback()
            job = db.get(IngestionJob, uuid.UUID(job_id))
            job.status = JobStatus.FAILED
            job.finished_at = _now()
            job.error_message = str(exc)[:2000]
            job.document_version.status = ProcessingStatus.FAILED
            job.document_version.error_message = str(exc)[:2000]
            db.commit()
            raise