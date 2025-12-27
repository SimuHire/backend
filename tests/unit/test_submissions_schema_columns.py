import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_submissions_table_has_test_result_columns(db_engine):
    async with db_engine.begin() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("submissions")
        )
    names = {col["name"] for col in columns}
    required = {
        "tests_passed",
        "tests_failed",
        "test_output",
        "last_run_at",
        "commit_sha",
        "workflow_run_id",
        "diff_summary_json",
    }
    assert required.issubset(names)
