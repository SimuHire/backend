from __future__ import annotations

from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

from app.domains.github_native.artifacts.models import ParsedTestResults


def parse_junit(zf: ZipFile) -> ParsedTestResults | None:
    for name in zf.namelist():
        if not name.lower().endswith(".xml"):
            continue
        with zf.open(name) as fp:
            try:
                tree = ElementTree.parse(fp)
            except ElementTree.ParseError:
                continue
        passed, failed = _junit_counts(tree.getroot())
        total = passed + failed
        return ParsedTestResults(
            passed=passed,
            failed=failed,
            total=total,
            stdout=None,
            stderr=None,
            summary={"format": "junit"},
        )
    return None


def _junit_counts(root: Any) -> tuple[int, int]:
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
