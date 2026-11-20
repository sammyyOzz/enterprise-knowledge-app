from api.enums.enums import WorkspaceRole

ROLE_RANK = {
    WorkspaceRole.VIEWER: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.OWNER: 3,
}


def role_allows(actual: WorkspaceRole, minimum: WorkspaceRole) -> bool:
    """viewer < editor < owner: a role may do everything the lower roles can."""
    return ROLE_RANK[actual] >= ROLE_RANK[minimum]