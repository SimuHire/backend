from __future__ import annotations

import json
from typing import Any
from zipfile import ZipFile

from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.integrations.github.artifacts.models import ParsedTestResults


def parse_named_json(zf: ZipFile) -> ParsedTestResults | None:
    for name in zf.namelist():
        if name.endswith(f"{TEST_ARTIFACT_NAMESPACE}.json"):
            with zf.open(name) as fp:
                data = _safe_json_load(fp)
                if data:
                    return _build_result(data)
    return None


def parse_any_json(zf: ZipFile) -> ParsedTestResults | None:
    for name in zf.namelist():
        if name.lower().endswith(".json"):
            with zf.open(name) as fp:
                data = _safe_json_load(fp)
            if data and {"passed", "failed", "total"} <= set(data.keys()):
                return _build_result(data)
    return None


def _build_result(data: dict[str, Any]) -> ParsedTestResults:
    summary = data.get("summary")
    return ParsedTestResults(
        passed=int(data.get("passed") or 0),
        failed=int(data.get("failed") or 0),
        total=int(data.get("total") or 0),
        stdout=data.get("stdout"),
        stderr=data.get("stderr"),
        summary=summary if isinstance(summary, dict) else None,
    )


def _safe_json_load(fp) -> dict[str, Any] | None:
    try:
        data = json.load(fp)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
