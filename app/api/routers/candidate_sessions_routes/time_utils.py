from __future__ import annotations

from datetime import UTC, datetime


def utcnow():
    return datetime.now(UTC)


__all__ = ["utcnow"]
