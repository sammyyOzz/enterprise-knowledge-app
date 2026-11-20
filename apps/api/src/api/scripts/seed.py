"""
Create (or repair) a demo organization, admin user and workspace. Idempotent.
The admin password is synchronized with the configured value on every run.

    docker compose exec api python -m api.scripts.seed

The admin's password comes from SEED_ADMIN_PASSWORD (default below). Development only:
in a real deployment people sign up through the app.
"""

import os

from sqlalchemy import select

import api.models  # noqa: F401  (registers all models)
from api.auth.passwords import hash_password, verify_password
from api.core.database import SessionLocal
from api.enums.enums import UserRole, WorkspaceRole
from api.models.organization import Organization
from api.models.user import User
from api.models.workspace import Workspace
from api.models.workspace_member import WorkspaceMember

ORG_SLUG = "demo"
USER_EMAIL = "admin@example.com"
WORKSPACE_NAME = "Default Workspace"
DEFAULT_PASSWORD = "password"


def main() -> None:
    password = os.environ.get("SEED_ADMIN_PASSWORD", DEFAULT_PASSWORD)
    with SessionLocal() as db:
        org = db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        if org is None:
            org = Organization(name="Demo Organization", slug=ORG_SLUG)
            db.add(org)
            db.flush()

        user = db.scalar(select(User).where(User.email == USER_EMAIL))
        if user is None:
            user = User(
                organization_id=org.id,
                email=USER_EMAIL,
                hashed_password=hash_password(password),
                full_name="Demo Admin",
                role=UserRole.ADMIN,
            )
            db.add(user)
            db.flush()
        elif not verify_password(user.hashed_password, password):
            user.hashed_password = hash_password(password)

        workspace = db.scalar(
            select(Workspace).where(
                Workspace.organization_id == org.id, Workspace.name == WORKSPACE_NAME
            )
        )
        if workspace is None:
            workspace = Workspace(organization_id=org.id, name=WORKSPACE_NAME)
            db.add(workspace)
            db.flush()

        if db.get(WorkspaceMember, (workspace.id, user.id)) is None:
            db.add(
                WorkspaceMember(
                    workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
                )
            )

        db.commit()
        print(f"Sign in with  {USER_EMAIL}  /  {password}")
        print(f"workspace_id = {workspace.id}")


if __name__ == "__main__":
    main()