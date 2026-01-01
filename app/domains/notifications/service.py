from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Simulation
from app.services.email import EmailSendResult, EmailService

INVITE_EMAIL_RATE_LIMIT_SECONDS = 30
VERIFICATION_EMAIL_RATE_LIMIT_SECONDS = 60
VERIFICATION_CODE_TTL_MINUTES = 15


def _utc_now(now: datetime | None) -> datetime:
    resolved = now or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved


def _rate_limited(
    last_attempt: datetime | None, now: datetime, window_seconds: int
) -> bool:
    if last_attempt is None:
        return False
    last = last_attempt
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return (now - last).total_seconds() < window_seconds


def _sanitize_error(err: str | None) -> str | None:
    if not err:
        return None
    return err[:200]


def _invite_email_content(
    *,
    candidate_name: str,
    invite_url: str,
    simulation: Simulation,
    expires_at: datetime | None,
) -> tuple[str, str, str]:
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    expires_text = (
        expires_at.astimezone(UTC).strftime("%Y-%m-%d") if expires_at else "soon"
    )
    subject = f"You're invited: {simulation.title}"
    text = (
        f"Hi {candidate_name},\n\n"
        f"You've been invited to complete the {simulation.role} simulation.\n"
        f"Simulation: {simulation.title}\n"
        f"Role: {simulation.role}\n\n"
        f"Start here: {invite_url}\n\n"
        f"Your invite expires on {expires_text}. "
        "If you did not expect this email, you can ignore it."
    )
    html = (
        f"<p>Hi {candidate_name},</p>"
        f"<p>You have been invited to complete the <strong>{simulation.role}</strong> simulation.</p>"
        f"<p><strong>Simulation:</strong> {simulation.title}<br>"
        f"<strong>Role:</strong> {simulation.role}</p>"
        f'<p><a href="{invite_url}">Open your invite</a></p>'
        f"<p>This invite expires on {expires_text}.</p>"
    )
    return subject, text, html


def _verification_email_content(
    *,
    candidate_name: str,
    invite_url: str,
    code: str,
    expires_at: datetime,
) -> tuple[str, str, str]:
    expires_text = expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    subject = "Your SimuHire verification code"
    text = (
        f"Hi {candidate_name},\n\n"
        f"Use this code to verify your invite: {code}\n"
        f"Verification code expires at {expires_text}.\n\n"
        f"You can also open your invite directly: {invite_url}\n"
        "If you did not request this, you can ignore this email."
    )
    html = (
        f"<p>Hi {candidate_name},</p>"
        f"<p>Use this code to verify your invite:</p>"
        f"<h2>{code}</h2>"
        f"<p>This code expires at {expires_text}.</p>"
        f'<p><a href="{invite_url}">Open your invite</a></p>'
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    return subject, text, html


async def send_invite_email(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    simulation: Simulation,
    invite_url: str,
    email_service: EmailService,
    now: datetime | None = None,
) -> EmailSendResult:
    """Send an invite email and persist delivery status."""
    now = _utc_now(now)
    if _rate_limited(
        candidate_session.invite_email_last_attempt_at,
        now,
        INVITE_EMAIL_RATE_LIMIT_SECONDS,
    ):
        candidate_session.invite_email_status = "rate_limited"
        candidate_session.invite_email_last_attempt_at = now
        candidate_session.invite_email_error = "Rate limited"
        await db.commit()
        await db.refresh(candidate_session)
        return EmailSendResult(status="rate_limited", error="Rate limited")

    subject, text, html = _invite_email_content(
        candidate_name=candidate_session.candidate_name,
        invite_url=invite_url,
        simulation=simulation,
        expires_at=candidate_session.expires_at,
    )
    result = await email_service.send_email(
        to=candidate_session.invite_email,
        subject=subject,
        text=text,
        html=html,
    )

    candidate_session.invite_email_last_attempt_at = now
    if result.status == "sent":
        candidate_session.invite_email_status = "sent"
        candidate_session.invite_email_sent_at = now
        candidate_session.invite_email_error = None
    else:
        candidate_session.invite_email_status = result.status
        candidate_session.invite_email_error = _sanitize_error(result.error)

    await db.commit()
    await db.refresh(candidate_session)
    return result


async def send_verification_email(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    invite_url: str,
    email_service: EmailService,
    now: datetime | None = None,
) -> EmailSendResult:
    """Generate and send a verification code email, respecting rate limits."""
    now = _utc_now(now)
    if _rate_limited(
        candidate_session.verification_email_last_attempt_at,
        now,
        VERIFICATION_EMAIL_RATE_LIMIT_SECONDS,
    ):
        candidate_session.verification_email_status = "rate_limited"
        candidate_session.verification_email_last_attempt_at = now
        candidate_session.verification_email_error = "Rate limited"
        await db.commit()
        await db.refresh(candidate_session)
        return EmailSendResult(status="rate_limited", error="Rate limited")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)
    subject, text, html = _verification_email_content(
        candidate_name=candidate_session.candidate_name,
        invite_url=invite_url,
        code=code,
        expires_at=expires_at,
    )
    candidate_session.verification_code = code
    candidate_session.verification_code_sent_at = now
    candidate_session.verification_code_expires_at = expires_at

    result = await email_service.send_email(
        to=candidate_session.invite_email,
        subject=subject,
        text=text,
        html=html,
    )

    candidate_session.verification_email_last_attempt_at = now
    if result.status == "sent":
        candidate_session.verification_email_status = "sent"
        candidate_session.verification_email_error = None
    else:
        candidate_session.verification_email_status = result.status
        candidate_session.verification_email_error = _sanitize_error(result.error)

    await db.commit()
    await db.refresh(candidate_session)
    return result
