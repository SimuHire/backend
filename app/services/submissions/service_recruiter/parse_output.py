from __future__ import annotations

import json
from typing import Any


def parse_test_output(test_output: str | None) -> dict[str, Any] | str | None:
    """Parse stored test_output into a dict when JSON, else return raw string."""
    if not test_output:
        return None
    try:
        parsed = json.loads(test_output)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        return test_output
    return test_output
