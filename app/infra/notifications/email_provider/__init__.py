from __future__ import annotations

# NOTE: Providers are split by transport; imports stay stable for callers.
from .base import EmailMessage, EmailProvider, EmailSendError
from .console import ConsoleEmailProvider
from .helpers import parse_sender
from .memory import MemoryEmailProvider
from .resend import ResendEmailProvider
from .sendgrid import SendGridEmailProvider
from .smtp import SMTPEmailProvider

__all__ = [
    "ConsoleEmailProvider",
    "EmailMessage",
    "EmailProvider",
    "EmailSendError",
    "MemoryEmailProvider",
    "ResendEmailProvider",
    "SendGridEmailProvider",
    "SMTPEmailProvider",
    "parse_sender",
    "_parse_sender",
]

_parse_sender = parse_sender
