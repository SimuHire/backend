from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

PREFERRED_ARTIFACT_NAMES = {"simuhire-test-results", "test-results", "junit"}


@dataclass
class ParsedTestResults:
    """Normalized test results parsed from GitHub artifact."""

    passed: int
    failed: int
    total: int
    stdout: str | None = None
    stderr: str | None = None
    summary: dict[str, Any] | None = None


def parse_test_results_zip(content: bytes) -> ParsedTestResults | None:
    """Extract test results from a GitHub Actions artifact zip."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Prefer JSON file named simuhire-test-results.json
            for name in zf.namelist():
                if name.endswith("simuhire-test-results.json"):
                    with zf.open(name) as fp:
                        data = _safe_json_load(fp)
                        if data is None:
                            continue
                        return ParsedTestResults(
                            passed=int(data.get("passed") or 0),
                            failed=int(data.get("failed") or 0),
                            total=int(data.get("total") or 0),
                            stdout=data.get("stdout"),
                            stderr=data.get("stderr"),
                            summary=data.get("summary")
                            if isinstance(data.get("summary"), dict)
                            else None,
                        )

            # Next, look for any .json file with similar keys
            for name in zf.namelist():
                if name.lower().endswith(".json"):
                    with zf.open(name) as fp:
                        data = _safe_json_load(fp)
                        if data is None:
                            continue
                        if {"passed", "failed", "total"} <= set(data.keys()):
                            return ParsedTestResults(
                                passed=int(data.get("passed") or 0),
                                failed=int(data.get("failed") or 0),
                                total=int(data.get("total") or 0),
                                stdout=data.get("stdout"),
                                stderr=data.get("stderr"),
                                summary=data.get("summary")
                                if isinstance(data.get("summary"), dict)
                                else None,
                            )

            # Fallback: parse JUnit XML files
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    with zf.open(name) as fp:
                        try:
                            tree = ElementTree.parse(fp)
                        except ElementTree.ParseError:
                            continue
                        root = tree.getroot()
                        passed, failed = _junit_counts(root)
                        total = passed + failed
                        return ParsedTestResults(
                            passed=passed,
                            failed=failed,
                            total=total,
                            stdout=None,
                            stderr=None,
                            summary={"format": "junit"},
                        )
    except zipfile.BadZipFile:
        return None
    return None


def _safe_json_load(fp) -> dict[str, Any] | None:
    """Load JSON content, returning None on decode errors."""
    try:
        data = json.load(fp)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _junit_counts(root) -> tuple[int, int]:
    """Compute pass/fail counts from JUnit XML."""
    passed = 0
    failed = 0
    for testcase in root.iter("testcase"):
        failures = list(testcase.iter("failure"))
        errors = list(testcase.iter("error"))
        if failures or errors:
            failed += 1
        else:
            passed += 1
    return passed, failed
