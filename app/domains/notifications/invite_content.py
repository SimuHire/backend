from __future__ import annotations

from datetime import UTC, datetime

from app.core.brand import APP_NAME
from app.domains import Simulation


def sanitize_error(err: str | None) -> str | None:
    return err[:200] if err else None


def invite_email_content(
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
        f"You've been invited to complete the {simulation.role} simulation in {APP_NAME}.\n"
        f"Simulation: {simulation.title}\n"
        f"Role: {simulation.role}\n\n"
        f"Start here: {invite_url}\n\n"
        f"Your invite expires on {expires_text}. "
        "If you did not expect this email, you can ignore it."
    )
    html = (
        f"<p>Hi {candidate_name},</p>"
        f"<p>You have been invited to complete the <strong>{simulation.role}</strong> simulation in {APP_NAME}.</p>"
        f"<p><strong>Simulation:</strong> {simulation.title}<br>"
        f"<strong>Role:</strong> {simulation.role}</p>"
        f'<p><a href="{invite_url}">Open your invite</a></p>'
        f"<p>This invite expires on {expires_text}.</p>"
    )
    return subject, text, html
