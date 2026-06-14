from __future__ import annotations

from app.ai.ai_output_models import (
    ScenarioGenerationOutput,
    ScenarioRubric,
    ScenarioRubricDayWeights,
    ScenarioRubricDimension,
    ScenarioTaskPrompt,
)
from app.ai.ai_provider_clients_service import AIProviderExecutionError
from app.integrations.scenario_generation.anthropic_provider_client import (
    AnthropicScenarioGenerationProvider,
)
from app.integrations.scenario_generation.base_client import (
    ScenarioGenerationProviderRequest,
)


def _scenario_generation_output() -> ScenarioGenerationOutput:
    return ScenarioGenerationOutput(
        storyline_md="Short scenario",
        task_prompts_json=[
            ScenarioTaskPrompt(
                dayIndex=day_index,
                title=f"Day {day_index}",
                description=f"Do the work for day {day_index}.",
            )
            for day_index in range(1, 6)
        ],
        rubric_json=ScenarioRubric(
            summary="Short rubric",
            dayWeights=ScenarioRubricDayWeights(
                day1=10, day2=20, day3=30, day4=20, day5=20
            ),
            dimensions=[
                ScenarioRubricDimension(
                    name="Planning",
                    weight=15,
                    description="Plans well.",
                ),
                ScenarioRubricDimension(
                    name="Architecture",
                    weight=15,
                    description="Designs a workable structure.",
                ),
                ScenarioRubricDimension(
                    name="Problem Solving",
                    weight=15,
                    description="Resolves blockers effectively.",
                ),
                ScenarioRubricDimension(
                    name="Implementation",
                    weight=15,
                    description="Delivers the feature cleanly.",
                ),
                ScenarioRubricDimension(
                    name="Testing",
                    weight=10,
                    description="Verifies the behavior thoroughly.",
                ),
                ScenarioRubricDimension(
                    name="Communication",
                    weight=10,
                    description="Explains decisions clearly.",
                ),
                ScenarioRubricDimension(
                    name="Ownership",
                    weight=20,
                    description="Shows accountability end-to-end.",
                ),
            ],
        ),
        project_brief_md="# Project Brief\n\n## Business Context\n\nBuild the feature.\n",
    )


def test_anthropic_scenario_generation_provider_uses_larger_output_budget(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_call_anthropic_json(**kwargs):
        calls.append(kwargs)
        return _scenario_generation_output()

    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.call_anthropic_json",
        _fake_call_anthropic_json,
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.settings.ANTHROPIC_API_KEY",
        "anthropic-test-key",
    )

    provider = AnthropicScenarioGenerationProvider()
    response = provider.generate_scenario(
        request=ScenarioGenerationProviderRequest(
            agent_key="prestart",
            fallback_provider="openai",
            system_prompt="system",
            user_prompt="user",
            model="claude-3-5-sonnet-20241022",
        )
    )

    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 6_144
    assert response.model_name == "claude-3-5-sonnet-20241022"
    assert response.model_version == "claude-3-5-sonnet-20241022"
    assert response.result.storyline_md == "Short scenario"


def test_anthropic_scenario_generation_provider_uses_fallback_model_on_retryable_error(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_call_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"]))
        raise AIProviderExecutionError("anthropic_request_failed:RateLimitError")

    def _fake_call_openai_json_schema(**kwargs):
        calls.append(("openai", kwargs["model"]))
        return _scenario_generation_output()

    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.call_anthropic_json",
        _fake_call_anthropic_json,
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.call_openai_json_schema",
        _fake_call_openai_json_schema,
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.settings.ANTHROPIC_API_KEY",
        "anthropic-test-key",
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.settings.OPENAI_API_KEY",
        "openai-test-key",
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.anthropic_provider_client.settings.SCENARIO_GENERATION_FALLBACK_MODEL",
        "gpt-scenario-fallback",
    )

    provider = AnthropicScenarioGenerationProvider()
    response = provider.generate_scenario(
        request=ScenarioGenerationProviderRequest(
            agent_key="prestart",
            fallback_provider="openai",
            system_prompt="system",
            user_prompt="user",
            model="claude-3-5-sonnet-20241022",
        )
    )

    assert response.model_name == "gpt-scenario-fallback"
    assert response.model_version == "gpt-scenario-fallback"
    assert calls == [
        ("anthropic", "claude-3-5-sonnet-20241022"),
        ("openai", "gpt-scenario-fallback"),
    ]
