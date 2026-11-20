from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (registers all models)
from api.auth.tokens import hash_token, new_token
from api.core.config import app_config
from api.models.auth_session import AuthSession
from api.models.user import User

TOUCH_EVERY = timedelta(hours=1)  # don't write to the database on every single request


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(db: Session, user: User, user_agent: str | None) -> str:
    """Adds a session row (caller commits) and returns the raw token to put in the cookie."""
    token = new_token()
    now = _now()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(days=app_config.SESSION_TTL_DAYS),
            last_used_at=now,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return token


def find_user_by_token(db: Session, token: str) -> User | None:
    now = _now()
    row = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > now,
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    user, session = row
    if now - session.last_used_at > TOUCH_EVERY:
        session.last_used_at = now
        db.commit()
    return user


def delete_session(db: Session, token: str) -> None:
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is not None:
        db.delete(session)
        db.commit()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=app_config.SESSION_COOKIE_NAME,
        value=token,
        max_age=app_config.SESSION_TTL_DAYS * 86400,
        httponly=True,  # not readable from JavaScript, so XSS can't steal the session
        secure=app_config.COOKIE_SECURE,
        samesite=app_config.COOKIE_SAMESITE,
        domain=app_config.COOKIE_DOMAIN,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=app_config.SESSION_COOKIE_NAME,
        domain=app_config.COOKIE_DOMAIN,
        path="/",
        secure=app_config.COOKIE_SECURE,
        httponly=True,
        samesite=app_config.COOKIE_SAMESITE,
    )