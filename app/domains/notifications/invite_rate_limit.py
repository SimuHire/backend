from __future__ import annotations

from datetime import datetime

from app.domains.notifications.invite_time import (
    INVITE_EMAIL_RATE_LIMIT_SECONDS,
    rate_limited,
)
from app.services.email import EmailSendResult


def should_rate_limit(candidate_session, now: datetime) -> bool:
    return rate_limited(
        candidate_session.invite_email_last_attempt_at,
        now,
        INVITE_EMAIL_RATE_LIMIT_SECONDS,
    )


async def record_rate_limit(db, candidate_session, now: datetime) -> EmailSendResult:
    candidate_session.invite_email_status = "rate_limited"
    candidate_session.invite_email_last_attempt_at = now
    candidate_session.invite_email_error = "Rate limited"
    await db.commit()
    await db.refresh(candidate_session)
    return EmailSendResult(status="rate_limited", error="Rate limited")
