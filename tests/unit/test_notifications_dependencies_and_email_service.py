import pytest

from app.api.dependencies import notifications
from app.integrations.notifications.email_provider import (
    ConsoleEmailProvider,
    EmailSendError,
    ResendEmailProvider,
    SendGridEmailProvider,
    SMTPEmailProvider,
)
from app.services.email import EmailService


def _reset_email_cache():
    notifications.get_email_service.cache_clear()
    # Ensure downstream tests see the default console provider.
    notifications.settings.email.TENON_EMAIL_PROVIDER = "console"


def test_build_provider_variants(monkeypatch):
    monkeypatch.setattr(
        notifications.settings.email, "TENON_EMAIL_FROM", "noreply@test"
    )

    monkeypatch.setattr(notifications.settings.email, "TENON_EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(notifications.settings.email, "TENON_RESEND_API_KEY", "key")
    assert isinstance(notifications._build_provider(), ResendEmailProvider)

    monkeypatch.setattr(
        notifications.settings.email, "TENON_EMAIL_PROVIDER", "sendgrid"
    )
    monkeypatch.setattr(notifications.settings.email, "SENDGRID_API_KEY", "sg-key")
    assert isinstance(notifications._build_provider(), SendGridEmailProvider)

    monkeypatch.setattr(notifications.settings.email, "TENON_EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(notifications.settings.email, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(notifications.settings.email, "SMTP_PORT", 2525)
    assert isinstance(notifications._build_provider(), SMTPEmailProvider)

    monkeypatch.setattr(notifications.settings.email, "TENON_EMAIL_PROVIDER", "console")
    assert isinstance(notifications._build_provider(), ConsoleEmailProvider)


def test_get_email_service_is_cached(monkeypatch):
    _reset_email_cache()
    monkeypatch.setattr(notifications.settings.email, "TENON_EMAIL_PROVIDER", "console")
    service1 = notifications.get_email_service()

    # Change provider config; cached service should still be returned.
    monkeypatch.setattr(notifications.settings.email, "TENON_EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(notifications.settings.email, "TENON_RESEND_API_KEY", "key")
    service2 = notifications.get_email_service()

    assert service1 is service2
    _reset_email_cache()


class _FlakyProvider:
    def __init__(self):
        self.calls = 0

    async def send(self, message):
        self.calls += 1
        if self.calls == 1:
            raise EmailSendError("try again", retryable=True)
        return "msg-123"


class _FailingProvider:
    def __init__(self, retryable: bool):
        self.retryable = retryable
        self.calls = 0

    async def send(self, message):
        self.calls += 1
        raise EmailSendError("fatal", retryable=self.retryable)


@pytest.mark.asyncio
async def test_email_service_retries_then_succeeds():
    provider = _FlakyProvider()
    service = EmailService(provider, sender="noreply@test", max_attempts=3)

    result = await service.send_email(to="user@test", subject="Hi", text="Hello")

    assert result.status == "sent"
    assert result.message_id == "msg-123"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_email_service_reports_failure_when_not_retryable():
    provider = _FailingProvider(retryable=False)
    service = EmailService(provider, sender="noreply@test", max_attempts=2)

    result = await service.send_email(to="user@test", subject="Hi", text="Hello")

    assert result.status == "failed"
    assert "fatal" in (result.error or "")
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_email_service_stops_after_retryable_failures():
    provider = _FailingProvider(retryable=True)
    service = EmailService(provider, sender="noreply@test", max_attempts=2)

    result = await service.send_email(to="user@test", subject="Hi", text="Hello")

    assert result.status == "failed"
    assert provider.calls == 2
