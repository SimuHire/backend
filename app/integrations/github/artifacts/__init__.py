from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.integrations.github.artifacts.json_parser import (
    parse_any_json,
    parse_named_json,
)
from app.integrations.github.artifacts.junit_parser import parse_junit
from app.integrations.github.artifacts.models import ParsedTestResults
from app.integrations.github.artifacts.zip_parser import parse_test_results_zip

PREFERRED_ARTIFACT_NAMES = {TEST_ARTIFACT_NAMESPACE, "test-results", "junit"}

__all__ = [
    "ParsedTestResults",
    "PREFERRED_ARTIFACT_NAMES",
    "parse_any_json",
    "parse_named_json",
    "parse_junit",
    "parse_test_results_zip",
]
