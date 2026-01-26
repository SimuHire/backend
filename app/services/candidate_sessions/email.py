from __future__ import annotations


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()
