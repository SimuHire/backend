from __future__ import annotations

from datetime import UTC, datetime

INVITE_EMAIL_RATE_LIMIT_SECONDS = 30


def utc_now(now: datetime | None) -> datetime:
    resolved = now or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved


def rate_limited(
    last_attempt: datetime | None, now: datetime, window_seconds: int
) -> bool:
    if last_attempt is None:
        return False
    last = last_attempt if last_attempt.tzinfo else last_attempt.replace(tzinfo=UTC)
    return (now - last).total_seconds() < window_seconds
