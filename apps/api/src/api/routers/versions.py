import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.status import VersionStatusOut
from api.services.status import get_version_status

# Same prefix as the retry endpoint (POST /documents/versions/{id}/retry), so the two sit together.
router = APIRouter(prefix="/documents/versions", tags=["versions"])


@router.get("/{version_id}", response_model=VersionStatusOut)
def version_status(version_id: uuid.UUID, db: Session = Depends(get_db)):
    """Live status for one version: state, user-safe error, latest job stage, embedding progress."""
    result = get_version_status(db, version_id)
    if result is None:
        raise HTTPException(404, "Version not found")
    return result