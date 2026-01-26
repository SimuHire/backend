from __future__ import annotations

import json
from typing import Any


def parse_env_list(value: Any):
    """Allow empty string, JSON array, or comma-separated env values."""
    if value in (None, "", [], (), "[]", "null", "None"):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [p.strip() for p in text.split(",") if p.strip()]
    return value
