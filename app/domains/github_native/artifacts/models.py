from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedTestResults:
    """Normalized test results parsed from GitHub artifact."""

    passed: int
    failed: int
    total: int
    stdout: str | None = None
    stderr: str | None = None
    summary: dict[str, Any] | None = None
