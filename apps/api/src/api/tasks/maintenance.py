"""
Periodic clean-up of ingestion jobs that can never finish on their own.

Why this exists: when a worker process is killed (the 15-minute hard time limit, an OOM kill,
a crashed container) it cannot record a failure, so the job and its version would stay
RUNNING/PROCESSING forever. This task finds those jobs and marks them FAILED so the UI shows
an honest status and the user can retry.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select

import api.models  # noqa: F401  (registers all models)
from api.core.database import SessionLocal
from api.enums.enums import JobStatus, ProcessingStatus
from api.models.ingestion_job import IngestionJob
from api.tasks.celery import celery_app

logger = logging.getLogger(__name__)

# The ingestion task is hard-killed after 15 minutes, so a RUNNING job that hasn't been touched
# for 20 minutes is certainly dead (running jobs update their timestamp as they progress).
STALE_RUNNING_AFTER = timedelta(minutes=20)
# A QUEUED job normally starts within seconds; this generous limit covers a worker outage.
STALE_QUEUED_AFTER = timedelta(hours=1)

TIMED_OUT_MESSAGE = "Processing timed out. You can retry."
NEVER_STARTED_MESSAGE = "Processing did not start. You can retry."


@celery_app.task(name="maintenance.reap_stale_jobs")
def reap_stale_jobs() -> dict:
    now = datetime.now(timezone.utc)
    reaped = 0

    with SessionLocal() as db:
        stale_jobs = db.scalars(
            select(IngestionJob)
            .where(
                or_(
                    and_(
                        IngestionJob.status == JobStatus.RUNNING,
                        IngestionJob.updated_at < now - STALE_RUNNING_AFTER,
                    ),
                    and_(
                        IngestionJob.status == JobStatus.QUEUED,
                        IngestionJob.updated_at < now - STALE_QUEUED_AFTER,
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        ).all()

        for job in stale_jobs:
            message = (
                TIMED_OUT_MESSAGE if job.status == JobStatus.RUNNING else NEVER_STARTED_MESSAGE
            )
            job.status = JobStatus.FAILED
            job.finished_at = now
            job.error_message = f"Reaped: {message}"

            # Only fail the VERSION if this is its newest attempt. If someone already retried,
            # a newer job owns the version and must not be disturbed.
            newest_attempt = db.scalar(
                select(func.max(IngestionJob.attempt)).where(
                    IngestionJob.document_version_id == job.document_version_id
                )
            )
            version = job.document_version
            if job.attempt == newest_attempt and version.status in (
                ProcessingStatus.PENDING,
                ProcessingStatus.PROCESSING,
            ):
                version.status = ProcessingStatus.FAILED
                version.error_message = message

            reaped += 1
            logger.warning("Reaped stale job %s (attempt %d): %s", job.id, job.attempt, message)

        db.commit()

    return {"reaped": reaped}