from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "secret",
    "password",
    "set-cookie",
    "cookie",
}
_REDACT_PATTERNS = [
    (re.compile(r"(?i)bearer\s+\S+"), "Bearer [redacted]"),
    (re.compile(r"(?i)(api[-_]?key|token|secret)[:=]\s*[^\s]+"), r"\1=[redacted]"),
]


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(s in lowered for s in _SENSITIVE_KEYS)


def _redact_string(value: str) -> str:
    redacted = value
    for pattern, repl in _REDACT_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v) for v in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "[redacted]" if _is_sensitive_key(key) else _redact_value(value)
        for key, value in mapping.items()
    }


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = _redact_mapping(record.args)
        elif isinstance(record.args, tuple):
            record.args = _redact_value(record.args)
        if isinstance(record.msg, str) and not record.args:
            record.msg = _redact_string(record.msg)
        for key, value in list(record.__dict__.items()):
            if key in {"args", "msg"}:
                continue
            record.__dict__[key] = (
                "[redacted]" if _is_sensitive_key(key) else _redact_value(value)
            )
        return True


REDACTOR = RedactionFilter()

__all__ = [
    "RedactionFilter",
    "REDACTOR",
    "_redact_string",
    "_redact_value",
    "_redact_mapping",
    "_is_sensitive_key",
]
