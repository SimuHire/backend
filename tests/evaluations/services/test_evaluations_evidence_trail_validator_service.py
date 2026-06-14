from __future__ import annotations

import pytest

from app.evaluations.services.evaluations_services_evidence_trail_validator_service import (
    EvidenceTrailValidationError,
    validate_winoe_report_evidence_trail,
)
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
    build_winoe_report_validation_bundle,
)


def _bundle() -> object:
    return build_winoe_report_validation_bundle()


def _valid_report() -> dict[str, object]:
    return build_valid_winoe_report_json()


def test_validate_well_cited_report_passes() -> None:
    result = validate_winoe_report_evidence_trail(_valid_report(), bundle=_bundle())

    assert result.passed is True
    assert result.errors == []
    assert result.metadata["citationCountsByDimension"]["Architecture & Design"] == 2


def test_validate_dimension_with_one_citation_fails() -> None:
    report = _valid_report()
    report["citations"] = report["citations"][:1]

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Architecture & Design" in error for error in result.errors)


def test_validate_duplicate_citations_do_not_satisfy_coverage() -> None:
    report = _valid_report()
    report["citations"][0] = dict(report["citations"][1])

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Architecture & Design" in error for error in result.errors)


def test_validate_dimension_without_any_citations_fails() -> None:
    report = _valid_report()
    report["dimensions"] = [
        {
            "name": "Architecture & Design",
            "score": 8.5,
            "justification": "Grounded in the design doc.",
        }
    ]
    report["citations"] = [
        citation
        for citation in report["citations"]
        if citation["dimension"] != "Architecture & Design"
    ]

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("has only 0 citations" in error for error in result.errors)


def test_validate_dimension_with_only_non_resolving_citations_fails() -> None:
    report = _valid_report()
    report["dimensions"] = [
        {
            "name": "Architecture & Design",
            "score": 8.5,
            "justification": "Grounded in the design doc.",
        }
    ]
    report["citations"] = [
        {
            "dimension": "Architecture & Design",
            "artifact_type": "design_doc",
            "artifact_ref": "missing-design-doc.md:L1-L2",
            "excerpt": "Broken citation.",
        },
        {
            "dimension": "Architecture & Design",
            "artifact_type": "design_doc",
            "artifact_ref": "missing-design-doc.md:L3-L4",
            "excerpt": "Broken citation.",
        },
    ]

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Unresolvable" in error for error in result.errors)


def test_validate_broken_citation_range_fails() -> None:
    report = _valid_report()
    report["citations"] = [
        {
            "dimension": "Code Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "abc1234:src/a.ts:L20-L1",
            "excerpt": "Broken citation.",
        },
        {
            "dimension": "Code Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "def5678:src/b.ts:L1-L40",
            "excerpt": "Workflow evidence.",
        },
    ]
    report["dimensions"] = [
        {
            "name": "Code Quality",
            "score": 8.0,
            "justification": "Grounded in repository structure and workflow evidence.",
        }
    ]
    report["narrative_assessment"] = (
        "Code Quality reflects deliberate repository assembly. "
        "Evidence: abc1234:src/a.ts:L20-L1; def5678:src/b.ts:L1-L40."
    )

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Malformed line range" in error for error in result.errors)


def test_validate_sha_path_citation_with_missing_file_content_passes_with_warning() -> (
    None
):
    result = validate_winoe_report_evidence_trail(
        _valid_report(),
        bundle=_bundle(),
    )

    assert result.passed is True
    assert result.errors == []
    assert result.warnings
    assert result.metadata["citationWarnings"]


def test_validate_invalid_sha_fails() -> None:
    report = _valid_report()
    report["citations"][4]["artifact_ref"] = "badc0de:src/a.ts:L1-L2"

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Unresolvable commit SHA" in error for error in result.errors)


def test_validate_invalid_path_fails() -> None:
    report = _valid_report()
    report["citations"][4]["artifact_ref"] = "abc1234:src/missing.ts:L1-L2"

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Unresolvable code path" in error for error in result.errors)


def test_validate_workflow_citation_without_candidate_authorship_fails() -> None:
    report = _valid_report()
    report["citations"][5] = {
        "dimension": "Testing Discipline",
        "artifact_type": "tests",
        "artifact_ref": "abc1234:.github/workflows/winoe-evidence-capture.yml:L1-L40",
        "excerpt": "Workflow evidence.",
    }

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("Unresolvable code path" in error for error in result.errors)


def test_validate_workflow_citation_with_candidate_authorship_passes() -> None:
    report = _valid_report()
    report["citations"][4][
        "artifact_ref"
    ] = "fedcba9:.github/workflows/winoe-evidence-capture.yml:L1-L2"
    bundle = build_winoe_report_validation_bundle(include_workflow_path=True)

    result = validate_winoe_report_evidence_trail(report, bundle=bundle)

    assert result.passed is True
    assert result.errors == []


def test_validate_generic_readme_without_proof_fails() -> None:
    report = _valid_report()
    report["citations"][4]["artifact_ref"] = "README.md:L1-L2"

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any(
        "Unresolvable markdown citation path" in error for error in result.errors
    )


def test_validate_uncited_paragraph_fails() -> None:
    report = _valid_report()
    report["narrative_assessment"] = "A paragraph without a citation."

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("missing a citation" in error for error in result.errors)


def test_validate_forbidden_term_in_prose_fails() -> None:
    report = _valid_report()
    report["verdict_one_liner"] = "Reject the candidate."

    result = validate_winoe_report_evidence_trail(report, bundle=_bundle())

    assert result.passed is False
    assert any("forbidden term" in error for error in result.errors)


def test_validation_error_carries_validation_result() -> None:
    result = validate_winoe_report_evidence_trail(
        {"dimensions": [], "citations": []},
        bundle=_bundle(),
    )

    with pytest.raises(EvidenceTrailValidationError) as exc_info:
        raise EvidenceTrailValidationError(result)

    assert exc_info.value.error_code == "evidence_trail_validation_failed"
    assert exc_info.value.validation_result is result
