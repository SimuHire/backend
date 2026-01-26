from __future__ import annotations

from functools import lru_cache

from app.core.settings import settings
from app.integrations.notifications.email_provider import (
    ConsoleEmailProvider,
    EmailProvider,
    ResendEmailProvider,
    SendGridEmailProvider,
    SMTPEmailProvider,
)
from app.services.email import EmailService


def _build_provider() -> EmailProvider:
    email_cfg = settings.email
    provider_name = (email_cfg.TENON_EMAIL_PROVIDER or "console").strip().lower()
    sender = email_cfg.TENON_EMAIL_FROM or "Tenon <notifications@tenon.com>"

    if provider_name == "resend":
        return ResendEmailProvider(
            email_cfg.TENON_RESEND_API_KEY, sender=sender, transport=None
        )
    if provider_name == "sendgrid":
        return SendGridEmailProvider(
            email_cfg.SENDGRID_API_KEY, sender=sender, transport=None
        )
    if provider_name == "smtp":
        return SMTPEmailProvider(
            email_cfg.SMTP_HOST,
            email_cfg.SMTP_PORT,
            username=email_cfg.SMTP_USERNAME,
            password=email_cfg.SMTP_PASSWORD,
            use_tls=bool(email_cfg.SMTP_TLS),
            sender=sender,
        )

    return ConsoleEmailProvider(sender=sender)


@lru_cache
def get_email_service() -> EmailService:
    """Build a singleton EmailService using configured provider."""
    provider = _build_provider()
    sender = settings.email.TENON_EMAIL_FROM or "Tenon <notifications@tenon.com>"
    return EmailService(provider, sender=sender, max_attempts=2)
