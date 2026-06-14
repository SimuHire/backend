"""Application module for trials services trials scenario generation service workflows."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.ai import (
    build_required_snapshot_prompt,
    require_agent_policy_snapshot,
    require_agent_runtime,
    require_ai_policy_snapshot,
)
from app.config import settings
from app.integrations.scenario_generation import (
    ScenarioGenerationProviderError,
    ScenarioGenerationProviderRequest,
    get_scenario_generation_provider,
)
from app.trials.services.trials_services_trials_scenario_generation_constants import (
    SCENARIO_GENERATION_JOB_TYPE,
    SCENARIO_PROMPT_VERSION,
    SCENARIO_RUBRIC_VERSION,
    SCENARIO_SOURCE_DETERMINISTIC_FALLBACK,
    SCENARIO_SOURCE_LLM,
)
from app.trials.services.trials_services_trials_scenario_generation_env_service import (
    choose_generation_source,
    is_demo_mode_enabled,
    llm_credentials_available,
)
from app.trials.services.trials_services_trials_scenario_generation_model import (
    GeneratedScenarioPayload,
    ScenarioGenerationMetadata,
)
from app.trials.services.trials_services_trials_scenario_generation_runtime_service import (
    build_deterministic_template_scenario as _build_deterministic_impl,
)
from app.trials.services.trials_services_trials_scenario_generation_runtime_service import (
    generate_scenario_payload as _generate_payload_impl,
)
from app.trials.services.trials_services_trials_scenario_generation_updates_service import (
    apply_generated_task_updates,
)

logger = logging.getLogger(__name__)

# Scenario generation is the first live AI gate in a brand-new trial. Give
# the worker enough retry budget to absorb brief provider throttling without
# dead-lettering the trial before it ever becomes invite-ready.
SCENARIO_GENERATION_JOB_MAX_ATTEMPTS = 7

_RETRYABLE_SCENARIO_GENERATION_ERROR_MARKERS = (
    "openai_request_failed:ratelimiterror",
    "openai_request_failed:apitimeouterror",
    "openai_request_failed:apiconnectionerror",
    "openai_request_failed:internalservererror",
    "openai_request_failed:serviceunavailableerror",
    "openai_request_failed:overloadederror",
    "rate limit",
    "too many requests",
    "429",
)


def _pick(options: tuple[str, ...], seed: int, salt: int) -> str:
    if not options:
        return ""
    index = (seed + (salt * 7919)) % len(options)
    return options[index]


def _preferred_language_framework(
    *,
    company_context: dict[str, Any] | None,
    company_prompt_overrides_json: dict[str, Any] | None,
    trial_prompt_overrides_json: dict[str, Any] | None,
    preferred_language_framework: str | None,
) -> str | None:
    if (
        preferred_language_framework is not None
        and preferred_language_framework.strip()
    ):
        return preferred_language_framework.strip()
    for payload in (
        company_context,
        company_prompt_overrides_json,
        trial_prompt_overrides_json,
    ):
        if not isinstance(payload, dict):
            continue
        for key in ("preferred_language_framework", "preferredLanguageFramework"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _is_retryable_scenario_generation_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    if not message:
        return False
    return any(
        marker in message for marker in _RETRYABLE_SCENARIO_GENERATION_ERROR_MARKERS
    )


def build_deterministic_template_scenario(
    *,
    role: str,
    preferred_language_framework: str,
    template_key: str,
    company_context: dict[str, Any] | None = None,
    focus: str | None = None,
    ai_policy_snapshot_json: dict[str, Any] | None = None,
) -> GeneratedScenarioPayload:
    """Build deterministic scenario."""
    return _build_deterministic_impl(
        role=role,
        template_key=template_key,
        company_context=company_context,
        focus=focus,
        preferred_language_framework=preferred_language_framework,
        ai_policy_snapshot_json=ai_policy_snapshot_json,
        pick=_pick,
    )


def _generate_with_llm(
    *,
    role: str,
    template_key: str,
    focus: str | None = None,
    company_context: dict[str, Any] | None = None,
    company_prompt_overrides_json: dict[str, Any] | None = None,
    trial_prompt_overrides_json: dict[str, Any] | None = None,
    preferred_language_framework: str | None = None,
    ai_policy_snapshot_json: dict[str, Any] | None = None,
) -> GeneratedScenarioPayload:
    require_ai_policy_snapshot(ai_policy_snapshot_json)
    normalized_company_overrides = company_prompt_overrides_json or None
    normalized_trial_overrides = trial_prompt_overrides_json or None
    resolved_preferred_language_framework = _preferred_language_framework(
        company_context=company_context,
        company_prompt_overrides_json=normalized_company_overrides,
        trial_prompt_overrides_json=normalized_trial_overrides,
        preferred_language_framework=preferred_language_framework,
    )
    run_context_md = (
        f"Role: {role}\n"
        "Project brief guidance: blank-repo, from-scratch system design only.\n"
        "Treat any Talent Partner context as optional and non-binding."
    )
    if normalized_company_overrides is not None:
        run_context_md += "\nCompany prompt overrides: " + json.dumps(
            normalized_company_overrides, sort_keys=True
        )
    if normalized_trial_overrides is not None:
        run_context_md += "\nTrial prompt overrides: " + json.dumps(
            normalized_trial_overrides, sort_keys=True
        )
    if resolved_preferred_language_framework is not None:
        run_context_md += (
            "\nPreferred language/framework context (non-binding): "
            f"{resolved_preferred_language_framework}"
        )
    system_prompt, rubric_prompt = build_required_snapshot_prompt(
        snapshot_json=ai_policy_snapshot_json,
        agent_key="prestart",
        run_context_md=run_context_md,
    )
    user_prompt = json.dumps(
        {
            "role": role,
            "focus": (focus or "").strip() or None,
            "companyContext": company_context or None,
            "companyPromptOverrides": normalized_company_overrides,
            "trialPromptOverrides": normalized_trial_overrides,
            "preferredLanguageFramework": (
                {
                    "value": resolved_preferred_language_framework,
                    "binding": "context_only",
                }
                if resolved_preferred_language_framework is not None
                else None
            ),
            "rubricGuidance": rubric_prompt,
        },
        indent=2,
        sort_keys=True,
    )
    runtime = require_agent_runtime(ai_policy_snapshot_json, "prestart")
    provider = get_scenario_generation_provider(str(runtime["provider"]))
    snapshot_agent = require_agent_policy_snapshot(ai_policy_snapshot_json, "prestart")
    request = ScenarioGenerationProviderRequest(
        agent_key="prestart",
        fallback_provider=str(settings.SCENARIO_GENERATION_FALLBACK_PROVIDER or ""),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=str(runtime["model"]),
    )
    try:
        response = provider.generate_scenario(request=request)
    except ScenarioGenerationProviderError as exc:
        raise RuntimeError(str(exc)) from exc
    logger.info(
        "scenario_generation_llm_completed",
        extra={"role": role, "trialKey": template_key},
    )
    return GeneratedScenarioPayload(
        storyline_md=response.result.storyline_md,
        task_prompts_json=[
            prompt.model_dump() for prompt in response.result.task_prompts_json
        ],
        project_brief_md=response.result.project_brief_md,
        rubric_json=response.result.rubric_json.model_dump(by_alias=True),
        ai_policy_snapshot_json=ai_policy_snapshot_json,
        metadata=ScenarioGenerationMetadata(
            source=SCENARIO_SOURCE_LLM,
            model_name=response.model_name,
            model_version=response.model_version,
            prompt_version=str(snapshot_agent["promptVersion"]),
            rubric_version=str(snapshot_agent["rubricVersion"]),
            template_key=template_key,
        ),
    )


def generate_scenario_payload(
    *,
    role: str,
    preferred_language_framework: str,
    template_key: str,
    focus: str | None = None,
    company_context: dict[str, Any] | None = None,
    company_prompt_overrides_json: dict[str, Any] | None = None,
    trial_prompt_overrides_json: dict[str, Any] | None = None,
    ai_policy_snapshot_json: dict[str, Any] | None = None,
) -> GeneratedScenarioPayload:
    """Generate scenario payload."""
    return _generate_payload_impl(
        role=role,
        preferred_language_framework=preferred_language_framework,
        template_key=template_key,
        choose_source=choose_generation_source,
        generate_with_llm=_generate_with_llm,
        build_fallback=build_deterministic_template_scenario,
        logger=logger,
        focus=focus,
        company_context=company_context,
        company_prompt_overrides_json=company_prompt_overrides_json,
        trial_prompt_overrides_json=trial_prompt_overrides_json,
        ai_policy_snapshot_json=ai_policy_snapshot_json,
    )


__all__ = [
    "SCENARIO_GENERATION_JOB_MAX_ATTEMPTS",
    "SCENARIO_GENERATION_JOB_TYPE",
    "SCENARIO_PROMPT_VERSION",
    "SCENARIO_RUBRIC_VERSION",
    "SCENARIO_SOURCE_LLM",
    "SCENARIO_SOURCE_DETERMINISTIC_FALLBACK",
    "ScenarioGenerationMetadata",
    "GeneratedScenarioPayload",
    "is_demo_mode_enabled",
    "llm_credentials_available",
    "choose_generation_source",
    "build_deterministic_template_scenario",
    "generate_scenario_payload",
    "apply_generated_task_updates",
]
