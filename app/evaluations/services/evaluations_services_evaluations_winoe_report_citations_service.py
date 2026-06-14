"""Winoe Report citation retrieval service."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.services.evaluations_services_evaluations_winoe_report_access_service import (
    get_candidate_session_evaluation_context,
    has_company_access,
)
from app.shared.database.shared_database_models_model import Submission, Task
from app.submissions.repositories import (
    winoe_report_citation_repository as winoe_report_citations_repo,
)
from app.submissions.repositories import (
    winoe_report_repository,
)

_MARKDOWN_RANGE_RE = re.compile(
    r"^(?:(?P<sha>[0-9a-fA-F]{7,40}):)?(?P<path>[^:\[\]]+):L(?P<start>\d+)-L(?P<end>\d+)$"
)
_TIMESTAMP_RANGE_RE = re.compile(r"^\[(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})\]$")


async def _load_report_context(db: AsyncSession, *, report_id: int) -> tuple[Any, Any]:
    report = await winoe_report_repository.get_by_id(db, report_id=report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Winoe Report not found"
        )
    context = await get_candidate_session_evaluation_context(
        db, candidate_session_id=report.candidate_session_id
    )
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Winoe Report not found"
        )
    return report, context


def _submission_day_map(
    submissions: list[tuple[Submission, Task]],
) -> dict[int, Submission]:
    by_day: dict[int, Submission] = {}
    for submission, task in submissions:
        day_index = getattr(task, "day_index", None)
        if isinstance(day_index, int):
            by_day[day_index] = submission
    return by_day


def _view_url_for_citation(
    *,
    citation: Any,
    submissions_by_day: dict[int, Submission],
) -> str | None:
    artifact_ref = getattr(citation, "artifact_ref", "") or ""
    artifact_type = getattr(citation, "artifact_type", "") or ""

    if artifact_ref.startswith("["):
        submission = submissions_by_day.get(4)
        if submission is None:
            return None
        return f"/api/submissions/{submission.id}"

    if artifact_ref.startswith("day1"):
        submission = submissions_by_day.get(1)
    elif artifact_ref.startswith("day3"):
        submission = submissions_by_day.get(3)
    elif artifact_ref.startswith("day4"):
        submission = submissions_by_day.get(4)
    elif artifact_ref.startswith("day5"):
        submission = submissions_by_day.get(5)
    elif artifact_type == "code_implementation":
        submission = submissions_by_day.get(3) or submissions_by_day.get(2)
    elif artifact_type == "submission":
        submission = (
            submissions_by_day.get(1)
            if artifact_ref.startswith("day1")
            else submissions_by_day.get(3)
            if artifact_ref.startswith("day3")
            else submissions_by_day.get(4)
            if artifact_ref.startswith("day4")
            else submissions_by_day.get(5)
            if artifact_ref.startswith("day5")
            else None
        )
    else:
        submission = None

    if submission is None:
        return None

    return f"/api/submissions/{submission.id}"


def _artifact_range_for_citation(citation: Any) -> str | None:
    artifact_ref = getattr(citation, "artifact_ref", "") or ""
    markdown_match = _MARKDOWN_RANGE_RE.match(artifact_ref)
    if markdown_match is not None:
        return f"L{markdown_match.group('start')}-L{markdown_match.group('end')}"
    timestamp_match = _TIMESTAMP_RANGE_RE.match(artifact_ref)
    if timestamp_match is not None:
        return f"{timestamp_match.group('start')}-{timestamp_match.group('end')}"
    return None


async def get_report_citations(
    db: AsyncSession,
    *,
    report_id: int,
    dimension: str | None = None,
    user: Any | None = None,
) -> dict[str, Any]:
    report, context = await _load_report_context(db, report_id=report_id)
    if not has_company_access(
        trial_company_id=context.trial.company_id,
        expected_company_id=getattr(user, "company_id", None),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate Trial access forbidden",
        )

    submissions = (
        await db.execute(
            select(Submission, Task)
            .join(Task, Task.id == Submission.task_id)
            .where(Submission.candidate_session_id == context.candidate_session.id)
            .order_by(Task.day_index.asc(), Submission.id.asc())
        )
    ).all()
    submissions_by_day = _submission_day_map(submissions)

    citations = await winoe_report_citations_repo.list_report_citations(
        db,
        report_id=report.id,
        dimension=dimension,
    )
    payload_citations: list[dict[str, Any]] = []
    for citation in citations:
        view_url = _view_url_for_citation(
            citation=citation, submissions_by_day=submissions_by_day
        )
        payload_citations.append(
            {
                "citation_id": citation.id,
                "dimension": citation.dimension,
                "artifact_type": citation.artifact_type,
                "artifact_ref": citation.artifact_ref,
                "artifact_range": _artifact_range_for_citation(citation),
                "excerpt": citation.excerpt,
                "resolved_open_target": view_url,
                "view_url": view_url,
            }
        )
    return {
        "dimension": dimension,
        "citations": payload_citations,
        "report_id": report.id,
        "candidate_session_id": context.candidate_session.id,
        "trial_id": context.trial.id,
    }


__all__ = ["get_report_citations"]
