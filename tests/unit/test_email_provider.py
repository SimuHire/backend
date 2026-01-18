import json

import httpx
import pytest

from app.infra.notifications.email_provider import (
    EmailMessage,
    EmailSendError,
    ResendEmailProvider,
    SendGridEmailProvider,
    SMTPEmailProvider,
    _parse_sender,
)


def test_parse_sender_with_name():
    email, name = _parse_sender("Tenon <noreply@test.com>")
    assert email == "noreply@test.com"
    assert name == "Tenon"


def test_parse_sender_without_name():
    email, name = _parse_sender("noreply@test.com")
    assert email == "noreply@test.com"
    assert name is None


def test_parse_sender_empty():
    email, name = _parse_sender("")
    assert email == ""
    assert name is None


@pytest.mark.asyncio
async def test_resend_provider_success_with_html():
    def _handler(request):
        payload = json.loads(request.content)
        assert payload["from"] == "Sender <sender@test.com>"
        assert payload["to"] == ["to@test.com"]
        assert payload["subject"] == "Hello"
        assert payload["html"] == "<b>Hi</b>"
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json={"id": "msg-123"})

    transport = httpx.MockTransport(_handler)
    provider = ResendEmailProvider(
        api_key="key",
        sender="Sender <sender@test.com>",
        transport=transport,
    )
    message = EmailMessage(
        to="to@test.com",
        subject="Hello",
        text="Hi",
        html="<b>Hi</b>",
    )
    message_id = await provider.send(message)
    assert message_id == "msg-123"


@pytest.mark.asyncio
async def test_resend_provider_status_error():
    def _handler(_request):
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(_handler)
    provider = ResendEmailProvider(
        api_key="key",
        sender="sender@test.com",
        transport=transport,
    )
    with pytest.raises(EmailSendError) as excinfo:
        await provider.send(EmailMessage(to="to@test.com", subject="Hi", text="Body"))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_resend_provider_handles_bad_json():
    def _handler(_request):
        return httpx.Response(200, content=b"not-json")

    transport = httpx.MockTransport(_handler)
    provider = ResendEmailProvider(
        api_key="key",
        sender="sender@test.com",
        transport=transport,
    )
    message_id = await provider.send(
        EmailMessage(to="to@test.com", subject="Hi", text="Body")
    )
    assert message_id is None


@pytest.mark.asyncio
async def test_sendgrid_provider_success_with_name():
    def _handler(request):
        payload = json.loads(request.content)
        assert payload["from"]["email"] == "sender@test.com"
        assert payload["from"]["name"] == "Sender"
        return httpx.Response(202, headers={"X-Message-Id": "sg-1"})

    transport = httpx.MockTransport(_handler)
    provider = SendGridEmailProvider(
        api_key="key",
        sender="Sender <sender@test.com>",
        transport=transport,
    )
    message_id = await provider.send(
        EmailMessage(to="to@test.com", subject="Hi", text="Body")
    )
    assert message_id == "sg-1"


@pytest.mark.asyncio
async def test_sendgrid_provider_includes_html():
    def _handler(request):
        payload = json.loads(request.content)
        assert len(payload["content"]) == 2
        assert payload["content"][1]["type"] == "text/html"
        return httpx.Response(202, headers={"X-Message-Id": "sg-2"})

    transport = httpx.MockTransport(_handler)
    provider = SendGridEmailProvider(
        api_key="key",
        sender="sender@test.com",
        transport=transport,
    )
    message_id = await provider.send(
        EmailMessage(to="to@test.com", subject="Hi", text="Body", html="<b>Hi</b>")
    )
    assert message_id == "sg-2"


@pytest.mark.asyncio
async def test_sendgrid_provider_status_error():
    def _handler(_request):
        return httpx.Response(400)

    transport = httpx.MockTransport(_handler)
    provider = SendGridEmailProvider(
        api_key="key",
        sender="sender@test.com",
        transport=transport,
    )
    with pytest.raises(EmailSendError) as excinfo:
        await provider.send(EmailMessage(to="to@test.com", subject="Hi", text="Body"))
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_smtp_provider_send(monkeypatch):
    calls = {"starttls": 0, "login": 0, "send": 0}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            return None

        def starttls(self, context=None):
            calls["starttls"] += 1
            assert context is not None

        def login(self, username, password):
            calls["login"] += 1
            assert username == "user"
            assert password == "pass"

        def send_message(self, message):
            calls["send"] += 1
            assert message["To"] == "to@test.com"

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    provider = SMTPEmailProvider(
        host="smtp.test",
        username="user",
        password="pass",
        use_tls=True,
        sender="sender@test.com",
    )
    await provider.send(
        EmailMessage(to="to@test.com", subject="Hi", text="Body", html="<b>Body</b>")
    )
    assert calls["starttls"] == 1
    assert calls["login"] == 1
    assert calls["send"] == 1


def test_provider_validation_errors():
    with pytest.raises(ValueError):
        ResendEmailProvider("", sender="s")
    with pytest.raises(ValueError):
        SendGridEmailProvider("", sender="s")
    with pytest.raises(ValueError):
        SMTPEmailProvider("", sender="s")
