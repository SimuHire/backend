from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domain.submissions import service_candidate as svc


def test_validate_github_username_allows_standard():
    svc.validate_github_username("octocat")


def test_validate_github_username_rejects_bad():
    with pytest.raises(HTTPException):
        svc.validate_github_username("bad user")


def test_validate_repo_full_name():
    svc.validate_repo_full_name("owner/repo-name")
    with pytest.raises(HTTPException):
        svc.validate_repo_full_name("owner repo")


@pytest.mark.parametrize(
    "branch",
    [
        "feature/new-ui",
        "release-1.0",
    ],
)
def test_validate_branch_allows(branch):
    assert svc.validate_branch(branch) == branch


@pytest.mark.parametrize(
    "branch",
    [
        "feature//bad",
        "../secret",
        "/leading",
        "trailing/",
    ],
)
def test_validate_branch_rejects(branch):
    with pytest.raises(HTTPException):
        svc.validate_branch(branch)


def test_summarize_diff_includes_base_head():
    summary = svc.summarize_diff(
        {
            "files": [
                {
                    "filename": "a",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "changes": 1,
                }
            ]
        },
        base="base123",
        head="head123",
    )
    assert summary["base"] == "base123"
    assert summary["head"] == "head123"


def test_validate_run_allowed_blocks_non_code_tasks():
    class FakeTask:
        def __init__(self, task_type):
            self.type = task_type

    with pytest.raises(HTTPException):
        svc.validate_run_allowed(FakeTask("design"))
    # code tasks are allowed
    svc.validate_run_allowed(FakeTask("code"))
