from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def first_claim(
    claims: dict[str, Any], keys: Iterable[str], *, default: Any | None = None
):
    for key in keys:
        if key and key in claims:
            return claims[key]
    return default


def normalize_email(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()
