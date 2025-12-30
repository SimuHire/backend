import pytest
from fastapi import HTTPException

from app.api.routes import submissions
from tests.factories import create_recruiter


def test_derive_test_status_variants():
    assert submissions._derive_test_status(None, None, None) is None
    assert submissions._derive_test_status(None, 1, "oops") == "failed"
    assert submissions._derive_test_status(2, 0, "ok") == "passed"
    assert submissions._derive_test_status(None, None, "  logs  ") == "unknown"


@pytest.mark.asyncio
async def test_get_submission_detail_not_found(async_session):
    user = await create_recruiter(async_session, email="missing-sub@sim.com")
    with pytest.raises(HTTPException) as exc:
        await submissions.get_submission_detail(
            submission_id=9999, db=async_session, user=user
        )
    assert exc.value.status_code == 404
