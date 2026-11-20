"""FastAPI dependencies and helpers for authentication and workspace authorization."""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.auth.roles import role_allows
from api.auth.sessions import find_user_by_token
from api.core.config import app_config
from api.core.database import get_db
from api.enums.enums import WorkspaceRole
from api.models.document import Document
from api.models.document_version import DocumentVersion
from api.models.user import User
from api.models.workspace_member import WorkspaceMember


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(app_config.SESSION_COOKIE_NAME)
    user = find_user_by_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Not signed in")
    return user


def authorize_workspace(
    db: Session,
    user: User,
    workspace_id: uuid.UUID,
    minimum: WorkspaceRole = WorkspaceRole.VIEWER,
) -> WorkspaceMember:
    """
    Raises unless `user` belongs to the workspace with at least the `minimum` role.
    Non-members get a 404 (not 403) so the existence of other workspaces isn't revealed.
    """
    member = db.get(WorkspaceMember, (workspace_id, user.id))
    if member is None:
        raise HTTPException(404, "Workspace not found")
    if not role_allows(member.role, minimum):
        raise HTTPException(403, "You don't have permission to do that in this workspace")
    return member


def version_workspace_id(db: Session, version_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(Document.workspace_id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(DocumentVersion.id == version_id)
    )