import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import api.models  # noqa: F401  (registers all models)
from api.auth.deps import authorize_workspace, current_user, version_workspace_id
from api.core.database import get_db
from api.enums.enums import WorkspaceRole
from api.models.document import Document
from api.models.user import User
from api.schemas.document import (
    DocumentDetailOut,
    DocumentOut,
    UploadResponse,
    VersionOut,
)
from api.exceptions import (
    FilenameConflict,
    InvalidFileContent,
    NotFound,
    QueueUnavailable,
    RetryNotAllowed,
    StorageUnavailable,
    UnsupportedFileType,
)
from api.services.ingestion import (
    UploadOutcome,
    UploadResult,
    ingest_upload,
    retry_version,
)

from api.core.config import app_config

router = APIRouter(prefix="/documents", tags=["documents"])


def _current_version(doc: Document):
    return next((v for v in doc.versions if v.version_number == doc.current_version), None)


def _to_out(doc: Document) -> DocumentOut:
    current = _current_version(doc)
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        current_version=doc.current_version,
        status=current.status if current else None,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_response(result: UploadResult) -> UploadResponse:
    return UploadResponse(
        outcome=result.outcome,
        document_id=result.document_id,
        version_id=result.version_id,
        version_number=result.version_number,
        version_status=result.version_status,
        job_id=result.job_id,
    )


@router.post("/upload", response_model=UploadResponse, status_code=202)
def upload_document(
    response: Response,
    workspace_id: uuid.UUID = Form(...),
    # Optional: upload this file as a NEW VERSION of an existing document, even if the
    # filename is different. If omitted, the filename identifies the document.
    document_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    authorize_workspace(db, user, workspace_id, WorkspaceRole.EDITOR)  # also 404s for unknown workspaces

    data = file.file.read(app_config.MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > app_config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {app_config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    try:
        result = ingest_upload(
            db,
            workspace_id=workspace_id,
            document_id=document_id,
            filename=file.filename,
            data=data,
            uploaded_by=user.id,
        )
    except UnsupportedFileType as exc:
        raise HTTPException(415, str(exc))
    except InvalidFileContent as exc:
        raise HTTPException(422, str(exc))
    except NotFound as exc:
        raise HTTPException(404, str(exc))
    except FilenameConflict as exc:
        raise HTTPException(409, str(exc))
    except RetryNotAllowed as exc:
        raise HTTPException(409, str(exc))
    except IntegrityError:
        # Two simultaneous first uploads of the same new filename raced on the unique constraint.
        raise HTTPException(409, "Conflicting upload, please retry")
    except (StorageUnavailable, QueueUnavailable) as exc:
        raise HTTPException(503, str(exc))

    if result.outcome == UploadOutcome.DUPLICATE:
        response.status_code = 200  # nothing was queued
    return _to_response(result)


@router.post("/versions/{version_id}/retry", response_model=UploadResponse, status_code=202)
def retry_version_processing(
    version_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace_id = version_workspace_id(db, version_id)
    if workspace_id is None:
        raise HTTPException(404, "Version not found")
    authorize_workspace(db, user, workspace_id, WorkspaceRole.EDITOR)

    try:
        result = retry_version(db, version_id)
    except NotFound as exc:
        raise HTTPException(404, str(exc))
    except RetryNotAllowed as exc:
        raise HTTPException(409, str(exc))
    except QueueUnavailable as exc:
        raise HTTPException(503, str(exc))
    return _to_response(result)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    workspace_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    authorize_workspace(db, user, workspace_id)
    docs = db.scalars(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .options(selectinload(Document.versions))
        .order_by(Document.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_to_out(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    doc = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.versions))
    )
    if doc is None:
        raise HTTPException(404, "Document not found")
    authorize_workspace(db, user, doc.workspace_id)

    base = _to_out(doc)
    return DocumentDetailOut(
        **base.model_dump(),
        versions=[VersionOut.model_validate(v) for v in doc.versions],
    )