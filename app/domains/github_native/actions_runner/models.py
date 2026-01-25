from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RunStatus = Literal["passed", "failed", "running", "error"]


@dataclass
class ActionsRunResult:
    """Normalized GitHub Actions run result."""

    status: RunStatus
    run_id: int
    conclusion: str | None
    passed: int | None
    failed: int | None
    total: int | None
    stdout: str | None
    stderr: str | None
    head_sha: str | None
    html_url: str | None
    raw: dict[str, Any] | None = None
    poll_after_ms: int | None = None

    @property
    def as_test_output(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "runId": self.run_id,
            "conclusion": self.conclusion,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.raw and "summary" in self.raw:
            payload["summary"] = self.raw.get("summary")
        return payload
