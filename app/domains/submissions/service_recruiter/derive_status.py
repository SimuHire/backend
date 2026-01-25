from __future__ import annotations

from typing import Any


def derive_test_status(
    passed: int | None, failed: int | None, output: dict[str, Any] | str | None
) -> str | None:
    """Summarize test results into a status string."""
    parsed: dict[str, Any] | None = output if isinstance(output, dict) else None
    if (
        passed is None
        and failed is None
        and (
            parsed is None
            and (not output or (isinstance(output, str) and not output.strip()))
        )
    ):
        return None
    if parsed:
        status_text = str(parsed.get("status") or "").lower()
        if parsed.get("timeout") is True:
            return "timeout"
        if status_text in {"passed", "failed", "timeout", "error"}:
            return status_text
    if failed is not None and failed > 0:
        return "failed"
    if passed is not None and (failed is None or failed == 0):
        return "passed"
    return "unknown"
