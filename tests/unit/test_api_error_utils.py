import json

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.api import error_utils
from app.integrations.github.client import GithubError


def test_api_error_handler_includes_details():
    exc = error_utils.ApiError(
        status_code=400,
        detail="bad",
        error_code="BAD",
        retryable=False,
        details={"a": 1},
    )
    resp = error_utils.api_error_handler(None, exc)
    assert resp.status_code == 400
    assert b'"details"' in resp.body


def test_map_github_error_rate_limited():
    api_err = error_utils.map_github_error(GithubError("rate", status_code=429))
    assert api_err.error_code == "GITHUB_RATE_LIMITED"
    assert api_err.retryable is True


def test_validation_error_handler_template_key(monkeypatch):
    # Build a minimal RequestValidationError with a templateKey location to trigger details.
    err = RequestValidationError(
        errors=[{"loc": ("body", "templateKey"), "msg": "Invalid templateKey"}]
    )
    resp = error_utils.validation_error_handler(Request(scope={"type": "http"}), err)
    payload = json.loads(resp.body.decode())
    assert payload["errorCode"] == "INVALID_TEMPLATE_KEY"
    assert "allowed" in payload["details"]
