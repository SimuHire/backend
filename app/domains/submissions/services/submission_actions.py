from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.domains.github_native.actions_runner import ActionsRunResult


def derive_actions_metadata(
    actions_result: ActionsRunResult | None, now: datetime
) -> dict[str, Any]:
    meta = {
        "tests_passed": None,
        "tests_failed": None,
        "test_output": None,
        "commit_sha": None,
        "workflow_run_id": None,
        "last_run_at": None,
    }
    if actions_result is None:
        return meta
    meta["tests_passed"] = actions_result.passed
    meta["tests_failed"] = actions_result.failed
    meta["test_output"] = json.dumps(actions_result.as_test_output, ensure_ascii=False)
    meta["last_run_at"] = now
    meta["commit_sha"] = actions_result.head_sha
    meta["workflow_run_id"] = str(actions_result.run_id)
    return meta
