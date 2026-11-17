"""
Upload handling: validate, hash, de-duplicate, version, store, record, enqueue.

How versions are decided
------------------------
A document is identified by the caller (`document_id`) or, if omitted, by its
filename within the workspace. Whether anything NEW is created is decided by content:

  target document exists, content == its CURRENT version   -> duplicate (nothing created)
                                                              (or re-queued if that version FAILED)
  target document exists, content differs from current     -> new version (also on reverts: A -> B -> A = v3)
  no target document, identical content already in the
  workspace (another document)                             -> duplicate (nothing created)
  no target document, new content                          -> new document, version 1
"""

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.enums.enums import JobStatus, ProcessingStatus
from api.models.document import Document
from api.models.document_version import DocumentVersion
from api.models.ingestion_job import IngestionJob
from api.tasks.ingestion import process_document_version
from api.utils.storage import delete_file, upload_file
from api.utils.file import resolve_mime, sanitize_filename, validate_content
from api.core.config import app_config
from api.exceptions import (
  FilenameConflict,
  NotFound,
  QueueUnavailable,
  RetryNotAllowed,
  StorageUnavailable,
)


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
class UploadOutcome(str, Enum):
    QUEUED = "queued"
    REQUEUED = "requeued"
    DUPLICATE = "duplicate"


@dataclass
class UploadResult:
    outcome: UploadOutcome
    document_id: UUID
    version_id: UUID
    version_number: int
    version_status: ProcessingStatus
    job_id: UUID | None = None


def _result(
    outcome: UploadOutcome, version: DocumentVersion, job: IngestionJob | None = None
) -> UploadResult:
    return UploadResult(
        outcome=outcome,
        document_id=version.document_id,
        version_id=version.id,
        version_number=version.version_number,
        version_status=version.status,
        job_id=job.id if job else None,
    )


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
def _lock_document(
    db: Session, workspace_id: UUID, document_id: UUID | None, filename: str
) -> Document | None:
    """
    Find the target document and lock its row, so two simultaneous uploads to the
    same document are serialised and can't be handed the same version number.
    """
    stmt = select(Document).where(Document.workspace_id == workspace_id)
    if document_id is not None:
        stmt = stmt.where(Document.id == document_id)
    else:
        stmt = stmt.where(Document.filename == filename)
    document = db.scalars(stmt.with_for_update()).first()
    if document is None and document_id is not None:
        raise NotFound("Document not found in this workspace")
    return document


def _current_version(db: Session, document: Document) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version,
        )
    )


def _find_version_by_hash(
    db: Session, workspace_id: UUID, content_hash: str
) -> DocumentVersion | None:
    return db.scalars(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.workspace_id == workspace_id,
            DocumentVersion.content_hash == content_hash,
        )
        .order_by(DocumentVersion.created_at.desc())
        .limit(1)
    ).first()


def _reset_for_retry(version: DocumentVersion) -> None:
    version.status = ProcessingStatus.PENDING
    version.error_message = None


def _new_job(db: Session, version: DocumentVersion) -> IngestionJob:
    last_attempt = db.scalar(
        select(func.max(IngestionJob.attempt)).where(
            IngestionJob.document_version_id == version.id
        )
    )
    job = IngestionJob(
        document_version_id=version.id,
        status=JobStatus.QUEUED,
        attempt=(last_attempt or 0) + 1,
    )
    db.add(job)
    db.flush()
    # Use the job id as the Celery task id so the two are always traceable.
    job.celery_task_id = str(job.id)
    return job


def _create_version(
    db: Session,
    document: Document,
    version_number: int,
    filename: str,
    mime_type: str,
    content_hash: str,
    data: bytes,
) -> tuple[DocumentVersion, str]:
    storage_key = f"{document.workspace_id}/{document.id}/v{version_number}/{filename}"
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        storage_key=storage_key,
        content_hash=content_hash,
        file_size=len(data),
        status=ProcessingStatus.PENDING,
    )
    db.add(version)
    db.flush()
    # Store the file before committing so a DB row never points at a missing object.
    try:
        upload_file(io.BytesIO(data), storage_key, mime_type)
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable("Object storage is unavailable") from exc
    return version, storage_key


def _enqueue(db: Session, job: IngestionJob, version: DocumentVersion) -> None:
    """Enqueue only AFTER commit, so the worker is guaranteed to find the rows."""
    try:
        process_document_version.apply_async(args=[str(job.id)], task_id=str(job.id))
    except Exception as exc:  # noqa: BLE001
        message = f"Could not enqueue task: {exc}"[:2000]
        job.status = JobStatus.FAILED
        job.error_message = message
        version.status = ProcessingStatus.FAILED
        version.error_message = message
        db.commit()
        raise QueueUnavailable("Processing queue is unavailable") from exc


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def ingest_upload(
    db: Session,
    *,
    workspace_id: UUID,
    filename: str | None,
    data: bytes,
    document_id: UUID | None = None,
    uploaded_by: UUID | None = None,
) -> UploadResult:
    filename = sanitize_filename(filename)
    mime_type = resolve_mime(filename)
    validate_content(filename, data)
    content_hash = hashlib.sha256(data).hexdigest()

    uploaded_key: str | None = None
    try:
        document = _lock_document(db, workspace_id, document_id, filename)

        if document is None:
            # ---- Brand-new document: dedupe against the whole workspace ----------
            existing = _find_version_by_hash(db, workspace_id, content_hash)
            if existing and existing.status != ProcessingStatus.FAILED:
                result = _result(UploadOutcome.DUPLICATE, existing)
                db.rollback()
                return result
            if existing:  # same content failed earlier: retry it
                version, outcome = existing, UploadOutcome.REQUEUED
                _reset_for_retry(version)
            else:
                document = Document(
                    workspace_id=workspace_id,
                    uploaded_by=uploaded_by,
                    filename=filename,
                    mime_type=mime_type,
                    current_version=1,
                )
                db.add(document)
                db.flush()
                version, uploaded_key = _create_version(
                    db, document, 1, filename, mime_type, content_hash, data
                )
                outcome = UploadOutcome.QUEUED
        else:
            # ---- Existing document: compare against ITS current version only -----
            current = _current_version(db, document)
            if current and current.content_hash == content_hash:
                if current.status != ProcessingStatus.FAILED:
                    result = _result(UploadOutcome.DUPLICATE, current)
                    db.rollback()
                    return result
                version, outcome = current, UploadOutcome.REQUEUED
                _reset_for_retry(version)
            else:
                if document.filename != filename:
                    clash = db.scalar(
                        select(Document.id).where(
                            Document.workspace_id == workspace_id,
                            Document.filename == filename,
                            Document.id != document.id,
                        )
                    )
                    if clash:
                        raise FilenameConflict(
                            f"Another document named '{filename}' already exists in this workspace"
                        )
                    document.filename = filename  # document follows its latest name
                document.mime_type = mime_type

                last = db.scalar(
                    select(func.max(DocumentVersion.version_number)).where(
                        DocumentVersion.document_id == document.id
                    )
                )
                version_number = (last or 0) + 1
                document.current_version = version_number
                version, uploaded_key = _create_version(
                    db, document, version_number, filename, mime_type, content_hash, data
                )
                outcome = UploadOutcome.QUEUED

        job = _new_job(db, version)
        db.commit()
    except Exception:
        db.rollback()
        if uploaded_key:
            try:
                delete_file(uploaded_key)  # don't leave orphaned objects behind
            except Exception:  # noqa: BLE001
                pass
        raise

    _enqueue(db, job, version)
    return _result(outcome, version, job)


def retry_version(db: Session, version_id: UUID) -> UploadResult:
    """Re-queue a FAILED version, or one stuck in PENDING/PROCESSING (e.g. worker died)."""
    version = db.scalars(
        select(DocumentVersion).where(DocumentVersion.id == version_id).with_for_update()
    ).first()
    if version is None:
        raise NotFound("Version not found")
    if version.status == ProcessingStatus.READY:
        raise RetryNotAllowed("Version is already processed")

    if version.status != ProcessingStatus.FAILED:
        latest = db.scalars(
            select(IngestionJob)
            .where(IngestionJob.document_version_id == version.id)
            .order_by(IngestionJob.attempt.desc())
            .limit(1)
        ).first()
        if latest and latest.updated_at > datetime.now(timezone.utc) - app_config.STALE_AFTER:
            raise RetryNotAllowed("Version is still being processed")

    _reset_for_retry(version)
    job = _new_job(db, version)
    db.commit()
    _enqueue(db, job, version)
    return _result(UploadOutcome.REQUEUED, version, job)