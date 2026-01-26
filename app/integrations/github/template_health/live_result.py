from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiveCheckResult:
    errors: list[str]
    workflow_run_id: int | None
    workflow_conclusion: str | None
    artifact_name_found: str | None
