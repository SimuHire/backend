from __future__ import annotations

import re

_TOKEN_REDACT_PATTERNS = [
    re.compile(r"gh[pous]_[A-Za-z0-9]{10,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"(Authorization:\s*Bearer)\s+[^\s]+", re.IGNORECASE),
    re.compile(r"(token)\s+[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
]


def redact_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for pattern in _TOKEN_REDACT_PATTERNS:
        redacted = (
            pattern.sub(lambda match: f"{match.group(1)} [redacted]", redacted)
            if pattern.groups
            else pattern.sub("[redacted]", redacted)
        )
    return redacted
