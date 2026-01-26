from __future__ import annotations

import io
import zipfile

from app.integrations.github.artifacts.json_parser import (
    parse_any_json,
    parse_named_json,
)
from app.integrations.github.artifacts.junit_parser import parse_junit
from app.integrations.github.artifacts.models import ParsedTestResults


def parse_test_results_zip(content: bytes) -> ParsedTestResults | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return parse_named_json(zf) or parse_any_json(zf) or parse_junit(zf)
    except zipfile.BadZipFile:
        return None
