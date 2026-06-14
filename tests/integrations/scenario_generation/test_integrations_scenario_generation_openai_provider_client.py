from __future__ import annotations

import pytest

from app.ai.ai_output_models import (
    ScenarioGenerationOutput,
    ScenarioRubric,
    ScenarioRubricDayWeights,
    ScenarioRubricDimension,
    ScenarioTaskPrompt,
)
from app.ai.ai_provider_clients_service import AIProviderExecutionError
from app.integrations.scenario_generation.base_client import (
    ScenarioGenerationProviderError,
    ScenarioGenerationProviderRequest,
)
from app.integrations.scenario_generation.openai_provider_client import (
    OpenAIScenarioGenerationProvider,
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


def test_openai_scenario_generation_provider_maps_success_and_errors(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_call_openai_json_schema(**kwargs):
        calls.append(kwargs)
        return _scenario_generation_output()

    monkeypatch.setattr(
        "app.integrations.scenario_generation.openai_provider_client.call_openai_json_schema",
        _fake_call_openai_json_schema,
    )
    monkeypatch.setattr(
        "app.integrations.scenario_generation.openai_provider_client.settings.OPENAI_API_KEY",
        "openai-test-key",
    )

    provider = OpenAIScenarioGenerationProvider()
    request = ScenarioGenerationProviderRequest(
        agent_key="prestart",
        fallback_provider="openai",
        system_prompt="system",
        user_prompt="user",
        model="gpt-test",
    )
    response = provider.generate_scenario(request=request)

    assert calls[0]["api_key"] == "openai-test-key"
    assert calls[0]["model"] == "gpt-test"
    assert calls[0]["response_model"] is ScenarioGenerationOutput
    assert response.model_name == "gpt-test"
    assert response.model_version == "gpt-test"
    assert response.result.project_brief_md.startswith("# Project Brief")

    def _raise_provider_error(**_kwargs):
        raise AIProviderExecutionError("openai_request_failed")

    monkeypatch.setattr(
        "app.integrations.scenario_generation.openai_provider_client.call_openai_json_schema",
        _raise_provider_error,
    )
    with pytest.raises(ScenarioGenerationProviderError, match="openai_request_failed"):
        provider.generate_scenario(request=request)
