from __future__ import annotations

import pytest

from app.ai import AggregatedWinoeReportOutput, DayReviewerOutput
from app.ai.ai_provider_clients_service import AIProviderExecutionError
from app.integrations.winoe_report_review import (
    WinoeReportAggregateRequest,
    WinoeReportDayReviewRequest,
)
from app.integrations.winoe_report_review import (
    anthropic_provider_client as anthropic_provider_module,
)
from app.integrations.winoe_report_review import (
    openai_provider_client as provider_module,
)


def _day_output(*, day_index: int) -> DayReviewerOutput:
    return DayReviewerOutput.model_validate(
        {
            "dayIndex": day_index,
            "score": 0.78,
            "summary": f"The candidate completed day {day_index}.",
            "rubricBreakdown": {"execution": 0.8, "communication": 0.76},
            "evidence": [
                {
                    "kind": "submission",
                    "ref": f"submission://day{day_index}",
                    "quote": f"Implemented the day {day_index} checkpoint.",
                    "dayIndex": day_index,
                }
            ],
            "strengths": ["Delivered the core fix."],
            "risks": ["Could tighten test coverage."],
        }
    )


def _aggregated_output(*, reason: str | None = None) -> AggregatedWinoeReportOutput:
    return AggregatedWinoeReportOutput.model_validate(
        {
            "winoe_score": 82.0,
            "verdict_one_liner": "The candidate delivered a credible positive signal.",
            "dimensions": [
                {
                    "name": "Execution",
                    "score": 8.4,
                    "justification": "Strong execution under constraints.",
                },
                {
                    "name": "Communication",
                    "score": 7.8,
                    "justification": "Communicated blockers and tradeoffs clearly.",
                },
                {
                    "name": "Testing Discipline",
                    "score": 7.2,
                    "justification": "Kept the validation path covered.",
                },
                {
                    "name": "Problem Understanding",
                    "score": 8.1,
                    "justification": "Understood the failure mode and the scope quickly.",
                },
                {
                    "name": "Implementation Quality",
                    "score": 8.0,
                    "justification": "The fix was focused and aligned with the contract.",
                },
                {
                    "name": "Code Quality",
                    "score": 7.9,
                    "justification": "Readable changes with minimal churn.",
                },
                {
                    "name": "Reflection & Ownership",
                    "score": 7.7,
                    "justification": "Adjusted approach after the first validation gap.",
                },
                {
                    "name": "Evidence Trail",
                    "score": 8.3,
                    "justification": "Citations support the reviewer conclusion.",
                },
            ],
            "narrative_assessment": reason
            or "The evidence supports a positive signal with manageable follow-up work.",
            "citations": [
                {
                    "dimension": "Execution",
                    "artifact_type": "submission",
                    "artifact_ref": "submission://day2",
                    "excerpt": "The candidate closed the blocking issue.",
                }
            ],
            "cohort_context": "Peer performance is within the expected band.",
        }
    )


def test_anthropic_winoe_report_review_day_uses_day1_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        raise AIProviderExecutionError("anthropic_request_failed:RateLimitError")

    def _fake_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        return _day_output(day_index=1)

    monkeypatch.setattr(
        anthropic_provider_module, "call_anthropic_json", _fake_anthropic_json
    )
    monkeypatch.setattr(
        anthropic_provider_module, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "ANTHROPIC_API_KEY", "anthropic-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "OPENAI_API_KEY", "openai-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings,
        "WINOE_REPORT_DAY1_FALLBACK_MODEL",
        "gpt-day1-fallback",
    )

    provider = anthropic_provider_module.AnthropicWinoeReportReviewProvider()
    result = provider.review_day(
        request=WinoeReportDayReviewRequest(
            agent_key="designDocReviewer",
            fallback_provider="openai",
            system_prompt="system",
            user_prompt="user",
            model="claude-sonnet-4-6",
        )
    )

    assert result.dayIndex == 1
    assert calls == [
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-day1-fallback"),
    ]


def test_anthropic_winoe_report_review_day_uses_day4_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        raise AIProviderExecutionError("anthropic_request_failed:RateLimitError")

    def _fake_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        return _day_output(day_index=4)

    monkeypatch.setattr(
        anthropic_provider_module, "call_anthropic_json", _fake_anthropic_json
    )
    monkeypatch.setattr(
        anthropic_provider_module, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "ANTHROPIC_API_KEY", "anthropic-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "OPENAI_API_KEY", "openai-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings,
        "WINOE_REPORT_DAY4_FALLBACK_MODEL",
        "gpt-day4-fallback",
    )

    provider = anthropic_provider_module.AnthropicWinoeReportReviewProvider()
    result = provider.review_day(
        request=WinoeReportDayReviewRequest(
            agent_key="demoPresentationReviewer",
            fallback_provider="openai",
            system_prompt="system",
            user_prompt="user",
            model="claude-sonnet-4-6",
        )
    )

    assert result.dayIndex == 4
    assert calls == [
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-day4-fallback"),
    ]


def test_anthropic_winoe_report_review_day_uses_day5_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        raise AIProviderExecutionError("anthropic_request_failed:RateLimitError")

    def _fake_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        return _day_output(day_index=5)

    monkeypatch.setattr(
        anthropic_provider_module, "call_anthropic_json", _fake_anthropic_json
    )
    monkeypatch.setattr(
        anthropic_provider_module, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "ANTHROPIC_API_KEY", "anthropic-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings, "OPENAI_API_KEY", "openai-test-key"
    )
    monkeypatch.setattr(
        anthropic_provider_module.settings,
        "WINOE_REPORT_DAY5_FALLBACK_MODEL",
        "gpt-day5-fallback",
    )

    provider = anthropic_provider_module.AnthropicWinoeReportReviewProvider()
    result = provider.review_day(
        request=WinoeReportDayReviewRequest(
            agent_key="reflectionEssayReviewer",
            fallback_provider="openai",
            system_prompt="system",
            user_prompt="user",
            model="claude-sonnet-4-6",
        )
    )

    assert result.dayIndex == 5
    assert calls == [
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-day5-fallback"),
    ]


def test_openai_winoe_report_review_day_uses_day23_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        raise AIProviderExecutionError("openai_request_failed:RateLimitError")

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        return _day_output(day_index=2)

    monkeypatch.setattr(
        provider_module, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(provider_module, "call_anthropic_json", _fake_anthropic_json)
    monkeypatch.setattr(provider_module.settings, "OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setattr(
        provider_module.settings, "ANTHROPIC_API_KEY", "anthropic-test-key"
    )
    monkeypatch.setattr(
        provider_module.settings,
        "WINOE_REPORT_DAY23_FALLBACK_MODEL",
        "claude-day23-fallback",
    )

    provider = provider_module.OpenAIWinoeReportReviewProvider()
    result = provider.review_day(
        request=WinoeReportDayReviewRequest(
            agent_key="codeImplementationReviewer",
            fallback_provider="anthropic",
            system_prompt="system",
            user_prompt="user",
            model="gpt-5.2-codex",
        )
    )

    assert result.dayIndex == 2
    assert calls == [
        ("openai", "gpt-5.2-codex"),
        ("anthropic", "claude-day23-fallback"),
    ]


def test_openai_winoe_report_aggregate_uses_aggregator_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        raise AIProviderExecutionError("openai_request_failed:RateLimitError")

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        return _aggregated_output()

    monkeypatch.setattr(
        provider_module, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(provider_module, "call_anthropic_json", _fake_anthropic_json)
    monkeypatch.setattr(provider_module.settings, "OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setattr(
        provider_module.settings, "ANTHROPIC_API_KEY", "anthropic-test-key"
    )
    monkeypatch.setattr(
        provider_module.settings,
        "WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL",
        "claude-agg-fallback",
    )

    provider = provider_module.OpenAIWinoeReportReviewProvider()
    result = provider.aggregate_winoe_report(
        request=WinoeReportAggregateRequest(
            agent_key="winoeReport",
            fallback_provider="anthropic",
            system_prompt="system",
            user_prompt="user",
            model="gpt-5.2",
        )
    )

    assert result.winoe_score == 82.0
    assert (
        result.verdict_one_liner
        == "The candidate delivered a credible positive signal."
    )
    assert calls == [
        ("openai", "gpt-5.2"),
        ("anthropic", "claude-agg-fallback"),
    ]
