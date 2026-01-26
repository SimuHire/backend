from __future__ import annotations

from .identity import extract_identity
from .model import Principal
from .permissions import build_permissions


def build_principal(claims: dict) -> Principal:
    sub, email, name, roles = extract_identity(claims)
    permissions = build_permissions(claims, roles)
    return Principal(
        sub=sub,
        email=email,
        name=name or email.split("@")[0],
        roles=roles,
        permissions=permissions,
        claims=claims,
    )
