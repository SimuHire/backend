from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Principal:
    """Authenticated principal derived from an Auth0 access token."""

    sub: str
    email: str
    name: str | None
    roles: list[str]
    permissions: list[str]
    claims: dict[str, Any] = field(repr=False)
