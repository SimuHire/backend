from __future__ import annotations

from app.core.settings import settings


def build_permissions(claims: dict, roles: list[str]) -> list[str]:
    permissions_claim = claims.get("permissions")
    if not isinstance(permissions_claim, list):
        permissions_claim = claims.get(settings.auth.AUTH0_PERMISSIONS_CLAIM) or []
    permissions = [p for p in permissions_claim if isinstance(p, str)]
    if not permissions:
        perm_str = claims.get(settings.auth.permissions_str_claim)
        if isinstance(perm_str, str) and perm_str.strip():
            permissions = [
                p.strip() for p in perm_str.replace(",", " ").split() if p.strip()
            ]
    if not permissions and roles:
        lowered = [r.lower() for r in roles]
        if any("recruiter" in r for r in lowered):
            permissions.append("recruiter:access")
        if any("candidate" in r for r in lowered):
            permissions.append("candidate:access")
    return permissions
