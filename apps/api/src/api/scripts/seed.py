"""
Create a demo organization, admin user and workspace (idempotent).

Run inside the api container:
    docker compose exec api python -m api.scripts.seed
"""

import api.models  # noqa: F401  (registers all models)
from api.core.database import SessionLocal
from api.enums.enums import UserRole, WorkspaceRole
from api.models.organization import Organization
from api.models.user import User
from api.models.workspace import Workspace
from api.models.workspace_member import WorkspaceMember
from sqlalchemy import select

ORG_SLUG = "demo"
USER_EMAIL = "admin@example.com"
WORKSPACE_NAME = "Default Workspace"


def main() -> None:
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
                # Placeholder, not a valid hash: nobody can log in with it.
                # Replace when you build authentication.
                hashed_password="!seed-placeholder",
                full_name="Demo Admin",
                role=UserRole.ADMIN,
            )
            db.add(user)
            db.flush()

        workspace = db.scalar(
            select(Workspace).where(
                Workspace.organization_id == org.id, Workspace.name == WORKSPACE_NAME
            )
        )
        if workspace is None:
            workspace = Workspace(organization_id=org.id, name=WORKSPACE_NAME)
            db.add(workspace)
            db.flush()

        member = db.get(WorkspaceMember, (workspace.id, user.id))
        if member is None:
            db.add(
                WorkspaceMember(
                    workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
                )
            )

        db.commit()
        print(f"organization_id = {org.id}")
        print(f"user_id         = {user.id}")
        print(f"workspace_id    = {workspace.id}   <-- use this for uploads")


if __name__ == "__main__":
    main()