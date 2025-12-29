from __future__ import annotations

import pytest

from app.domain.submissions import service_recruiter as svc


def test_derive_test_status_variants():
    assert svc.derive_test_status(None, None, None) is None
    assert svc.derive_test_status(1, 0, {}) == "passed"
    assert svc.derive_test_status(None, 2, {}) == "failed"
    assert svc.derive_test_status(None, None, {"timeout": True}) == "timeout"
    assert svc.derive_test_status(None, None, {"status": "error"}) == "error"


def test_parse_test_output_fallback():
    assert svc.parse_test_output(None) is None
    assert svc.parse_test_output("not-json") == "not-json"
    assert svc.parse_test_output('{"a": 1}') == {"a": 1}


@pytest.mark.asyncio
async def test_fetch_detail_not_found_raises(monkeypatch):
    class DummyResult:
        def first(self):
            return None

    class DummySession:
        async def execute(self, *_a, **_k):
            return DummyResult()

    with pytest.raises(Exception) as excinfo:
        await svc.fetch_detail(DummySession(), submission_id=1, recruiter_id=2)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_detail_returns_row(monkeypatch):
    expected = ("sub", "task", "cs", "sim")

    class DummyResult:
        def __init__(self, val):
            self.val = val

        def first(self):
            return self.val

    class DummySession:
        async def execute(self, *_a, **_k):
            return DummyResult(expected)

    row = await svc.fetch_detail(DummySession(), submission_id=1, recruiter_id=2)
    assert row == expected


def test_parse_test_output_non_dict_json():
    assert svc.parse_test_output("[]") == "[]"


@pytest.mark.asyncio
async def test_list_submissions_applies_filters():
    class DummyResult:
        def all(self):
            return [("row",)]

    class DummySession:
        def __init__(self):
            self.received = None

        async def execute(self, stmt):
            self.received = stmt
            return DummyResult()

    session = DummySession()
    rows = await svc.list_submissions(session, 1, candidate_session_id=2, task_id=3)
    assert rows == [("row",)]
    assert session.received is not None
