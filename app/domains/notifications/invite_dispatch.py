from __future__ import annotations

from datetime import datetime

from app.domains import Simulation
from app.domains.notifications.invite_content import invite_email_content, sanitize_error
from app.services.email import EmailSendResult, EmailService


async def dispatch_invite_email(
    email_service: EmailService,
    *,
    candidate_session,
    simulation: Simulation,
    invite_url: str,
) -> EmailSendResult:
    subject, text, html = invite_email_content(
        candidate_name=candidate_session.candidate_name,
        invite_url=invite_url,
        simulation=simulation,
        expires_at=candidate_session.expires_at,
    )
    return await email_service.send_email(
        to=candidate_session.invite_email,
        subject=subject,
        text=text,
        html=html,
    )


async def record_send_result(
    db, candidate_session, now: datetime, result: EmailSendResult
) -> EmailSendResult:
    candidate_session.invite_email_last_attempt_at = now
    if result.status == "sent":
        candidate_session.invite_email_status = "sent"
        candidate_session.invite_email_sent_at = now
        candidate_session.invite_email_error = None
    else:
        candidate_session.invite_email_status = result.status
        candidate_session.invite_email_error = sanitize_error(result.error)

    await db.commit()
    await db.refresh(candidate_session)
    return result
