import re
import uuid

from pydantic import BaseModel, Field, field_validator

from api.enums.enums import UserRole, WorkspaceRole

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email) or len(email) > 320:
        raise ValueError("Enter a valid email address")
    return email


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    organization_name: str = Field(min_length=2, max_length=255)

    _normalise_email = field_validator("email")(_clean_email)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _normalise_email = field_validator("email")(_clean_email)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: UserRole


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str


class WorkspaceAccessOut(BaseModel):
    id: uuid.UUID
    name: str
    role: WorkspaceRole


class MeOut(BaseModel):
    user: UserOut
    organization: OrganizationOut
    workspaces: list[WorkspaceAccessOut]