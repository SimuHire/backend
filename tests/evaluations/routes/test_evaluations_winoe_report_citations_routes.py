from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.submissions.repositories.submissions_repositories_submissions_winoe_report_model import (
    WinoeReport,
)
from tests.evaluations.routes.evaluations_winoe_report_api_utils import *
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
)


@pytest.mark.asyncio
async def test_winoe_report_citations_authorization_filter_and_shape_routes(
    async_client,
    async_session,
    auth_header_factory,
    candidate_header_factory,
    monkeypatch,
):
    talent_partner, candidate_session = await _seed_completed_candidate_session(
        async_session
    )

    monkeypatch.setattr(
        "app.evaluations.services.winoe_report_pipeline.evaluator_service.get_winoe_report_evaluator",
        lambda: SimpleNamespace(
            evaluate=AsyncMock(
                return_value=SimpleNamespace(
                    day_results=[
                        SimpleNamespace(
                            day_index=1,
                            score=0.8,
                            rubric_breakdown={"communication": 0.8},
                            evidence=[{"kind": "submission", "ref": "day-1"}],
                        )
                    ],
                    overall_winoe_score=0.82,
                    recommendation="strong_signal",
                    confidence=0.91,
                    report_json=build_valid_winoe_report_json(),
                    reviewer_reports=[],
                )
            )
        ),
    )

    generate = await async_client.post(
        f"/api/candidate_sessions/{candidate_session.id}/winoe_report/generate",
        headers=auth_header_factory(talent_partner),
    )
    assert generate.status_code == 202, generate.text

    handled = await _run_worker_once(async_session, worker_id="winoe-report-citations")
    assert handled is True

    marker = (
        await async_session.execute(
            select(WinoeReport).where(
                WinoeReport.candidate_session_id == candidate_session.id
            )
        )
    ).scalar_one_or_none()
    assert marker is not None

    fetch = await async_client.get(
        f"/api/reports/{marker.id}/citations",
        headers=auth_header_factory(talent_partner),
    )
    assert fetch.status_code == 200, fetch.text
    payload = fetch.json()
    assert payload["dimension"] is None
    assert isinstance(payload["citations"], list)
    assert len(payload["citations"]) >= 2
    first = payload["citations"][0]
    assert set(first) == {
        "artifact_range",
        "artifact_ref",
        "artifact_type",
        "citation_id",
        "dimension",
        "excerpt",
        "resolved_open_target",
        "view_url",
    }
    assert isinstance(first["citation_id"], int)
    assert first["dimension"] == "Architecture & Design"
    assert isinstance(first["artifact_type"], str)
    assert isinstance(first["artifact_ref"], str)
    assert isinstance(first["artifact_range"], str)
    assert isinstance(first["excerpt"], str)
    assert first["resolved_open_target"] == first["view_url"]
    assert first["view_url"].startswith("/api/submissions/")
    assert "/view" not in first["view_url"]

    targets_by_type = {
        item["artifact_type"]: item
        for item in payload["citations"]
        if item["resolved_open_target"]
    }
    for artifact_type in (
        "design_doc",
        "code_implementation",
        "transcript",
        "reflection",
    ):
        citation = targets_by_type[artifact_type]
        assert citation["artifact_range"]
        target = citation["resolved_open_target"]
        direct = await async_client.get(
            target,
            headers=auth_header_factory(talent_partner),
        )
        assert direct.status_code == 200, (artifact_type, target, direct.text)

        unauthenticated = await async_client.get(target)
        assert unauthenticated.status_code in {401, 403}

        candidate_forbidden = await async_client.get(
            target,
            headers=candidate_header_factory(candidate_session),
        )
        assert candidate_forbidden.status_code in {401, 403}

    filtered = await async_client.get(
        f"/api/reports/{marker.id}/citations",
        params={"dimension": "Architecture & Design"},
        headers=auth_header_factory(talent_partner),
    )
    assert filtered.status_code == 200, filtered.text
    filtered_payload = filtered.json()
    assert filtered_payload["dimension"] == "Architecture & Design"
    assert all(
        item["artifact_type"] == "design_doc" for item in filtered_payload["citations"]
    )
    assert all(
        item["dimension"] == "Architecture & Design"
        for item in filtered_payload["citations"]
    )

    outsider = await create_talent_partner(
        async_session,
        email="winoe-report-citation-outsider@test.com",
    )
    await async_session.commit()
    forbidden = await async_client.get(
        f"/api/reports/{marker.id}/citations",
        headers=auth_header_factory(outsider),
    )
    assert forbidden.status_code == 403

    missing = await async_client.get(
        "/api/reports/999999/citations",
        headers=auth_header_factory(talent_partner),
    )
    assert missing.status_code == 404
