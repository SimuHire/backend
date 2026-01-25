from __future__ import annotations

from app.domains.submissions.presenter.redaction import redact_text
from app.domains.submissions.presenter.truncate import truncate_output

_OUTPUT_WHITELIST_KEYS = {
    "passed",
    "failed",
    "total",
    "stdout",
    "stderr",
    "summary",
    "runId",
    "run_id",
    "conclusion",
    "timeout",
}


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def sanitize_stream(value: str | None, *, max_chars: int):
    if not isinstance(value, str):
        return None, None
    redacted = redact_text(value)
    return truncate_output(redacted, max_chars=max_chars)


__all__ = ["_safe_int", "_OUTPUT_WHITELIST_KEYS", "sanitize_stream"]
