import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.auth.deps import current_user
from api.auth.passwords import hash_password, needs_rehash, verify_dummy, verify_password
from api.auth.ratelimit import get_rate_limiter
from api.auth.sessions import clear_session_cookie, create_session, delete_session, set_session_cookie
from api.core.config import app_config
from api.core.database import get_db
from api.enums.enums import UserRole, WorkspaceRole
from api.models.organization import Organization
from api.models.user import User
from api.models.workspace import Workspace
from api.models.workspace_member import WorkspaceMember
from api.schemas.auth import (
    LoginRequest,
    MeOut,
    OrganizationOut,
    SignupRequest,
    UserOut,
    WorkspaceAccessOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
SIGNUP_ATTEMPTS = 10
SIGNUP_WINDOW_SECONDS = 60 * 60

BAD_CREDENTIALS = "Incorrect email or password."


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy, run uvicorn with --proxy-headers so this is the real client IP.
    return request.client.host if request.client else "unknown"


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def _check_rate_limit(key: str, limit: int, window: int) -> None:
    allowed, retry_after = get_rate_limiter().hit(key, limit, window)
    if not allowed:
        raise HTTPException(
            429,
            "Too many attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(retry_after)},
        )


def build_me(db: Session, user: User) -> MeOut:
    organization = db.get(Organization, user.organization_id)
    rows = db.execute(
        select(Workspace.id, Workspace.name, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).all()
    return MeOut(
        user=UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role),
        organization=OrganizationOut(id=organization.id, name=organization.name),
        workspaces=[WorkspaceAccessOut(id=r.id, name=r.name, role=r.role) for r in rows],
    )


@router.post("/signup", response_model=MeOut, status_code=201)
def signup(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Creates an organization, its first admin, and a default workspace, then signs the user in."""
    if not app_config.ALLOW_SIGNUP:
        raise HTTPException(403, "Sign-up is disabled")
    _check_rate_limit(f"signup:{_client_ip(request)}", SIGNUP_ATTEMPTS, SIGNUP_WINDOW_SECONDS)

    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise HTTPException(409, "An account with this email already exists.")

    try:
        organization = Organization(name=payload.organization_name.strip(), slug=_slug(payload.organization_name))
        db.add(organization)
        db.flush()

        user = User(
            organization_id=organization.id,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=(payload.full_name or "").strip() or None,
            role=UserRole.ADMIN,
        )
        workspace = Workspace(organization_id=organization.id, name="General")
        db.add_all([user, workspace])
        db.flush()

        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
        token = create_session(db, user, request.headers.get("user-agent"))
        db.commit()
    except IntegrityError:
        db.rollback()  # two sign-ups with the same email raced
        raise HTTPException(409, "An account with this email already exists.")

    set_session_cookie(response, token)
    return build_me(db, user)


@router.post("/login", response_model=MeOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter_key = f"login:{_client_ip(request)}:{payload.email}"
    _check_rate_limit(limiter_key, LOGIN_ATTEMPTS, LOGIN_WINDOW_SECONDS)

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        verify_dummy(payload.password)  # keep timing the same as a real check
        raise HTTPException(401, BAD_CREDENTIALS)
    if not user.is_active or not verify_password(user.hashed_password, payload.password):
        raise HTTPException(401, BAD_CREDENTIALS)

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)

    token = create_session(db, user, request.headers.get("user-agent"))
    db.commit()
    get_rate_limiter().reset(limiter_key)

    set_session_cookie(response, token)
    return build_me(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(app_config.SESSION_COOKIE_NAME)
    if token:
        delete_session(db, token)
    clear_session_cookie(response)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return build_me(db, user)