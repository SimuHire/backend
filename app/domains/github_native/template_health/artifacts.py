from __future__ import annotations

import io
import json
import zipfile

from app.core.brand import TEST_ARTIFACT_NAMESPACE


def _validate_test_results_schema(payload: dict[str, object]) -> bool:
    required = ["passed", "failed", "total", "stdout", "stderr"]
    if not all(key in payload for key in required):
        return False
    for key in ["passed", "failed", "total"]:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    for key in ["stdout", "stderr"]:
        if not isinstance(payload.get(key), str):
            return False
    summary = payload.get("summary")
    if summary is not None and not isinstance(summary, dict):
        return False
    return True


def _extract_test_results_json(content: bytes) -> dict[str, object] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.endswith(f"{TEST_ARTIFACT_NAMESPACE}.json"):
                    with zf.open(name) as fp:
                        try:
                            data = json.load(fp)
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                            return None
                        return data if isinstance(data, dict) else None
    except zipfile.BadZipFile:
        return None
    return None
