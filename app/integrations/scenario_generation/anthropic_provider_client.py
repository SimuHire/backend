"""Anthropic-backed scenario-generation provider."""

from __future__ import annotations

import logging

from app.ai import ScenarioGenerationOutput
from app.ai.ai_provider_clients_service import (
    AIProviderExecutionError,
    api_key_configured,
    call_anthropic_json,
    call_openai_json_schema,
)
from app.config import settings
from app.integrations.scenario_generation.base_client import (
    ScenarioGenerationProviderError,
    ScenarioGenerationProviderRequest,
    ScenarioGenerationProviderResponse,
)

logger = logging.getLogger(__name__)

_SUPPORTED_FALLBACK_PROVIDER = "openai"
_SUPPORTED_AGENT_KEY = "prestart"


def _fallback_openai_model() -> str:
    return str(settings.SCENARIO_GENERATION_FALLBACK_MODEL or "").strip()


def _normalized_provider(value: str) -> str:
    return str(value or "").strip().lower()


def _require_supported_fallback_provider(*, request_provider: str) -> None:
    normalized = _normalized_provider(request_provider)
    if normalized != _SUPPORTED_FALLBACK_PROVIDER:
        raise ScenarioGenerationProviderError(
            "unsupported_scenario_generation_fallback_provider:"
            f"anthropic:{request_provider}"
        )


def _require_supported_agent_key(*, agent_key: str) -> None:
    if _normalized_provider(agent_key) != _SUPPORTED_AGENT_KEY:
        raise ScenarioGenerationProviderError(
            f"unsupported_scenario_generation_agent:anthropic:{agent_key}"
        )


def _is_retryable_anthropic_error(exc: Exception) -> bool:
    normalized = str(exc).strip().lower()
    if not normalized:
        return False
    return normalized.startswith("anthropic_request_failed") or normalized.startswith(
        "anthropic_invalid_json_output"
    )


class AnthropicScenarioGenerationProvider:
    """Generate scenarios with Anthropic Messages API."""

    # The prestart scenario payload is larger than the other Anthropic JSON
    # contracts in this repo. A slightly higher output cap avoids truncating the
    # project brief while staying scoped to this provider.
    _MAX_TOKENS = 6_144

    def generate_scenario(
        self,
        *,
        request: ScenarioGenerationProviderRequest,
    ) -> ScenarioGenerationProviderResponse:
        _require_supported_agent_key(agent_key=request.agent_key)
        _require_supported_fallback_provider(request_provider=request.fallback_provider)
        served_model = request.model
        try:
            result = call_anthropic_json(
                api_key=settings.ANTHROPIC_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=ScenarioGenerationOutput,
                timeout_seconds=settings.SCENARIO_GENERATION_TIMEOUT_SECONDS,
                max_retries=settings.SCENARIO_GENERATION_MAX_RETRIES,
                max_tokens=self._MAX_TOKENS,
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_anthropic_error(exc) or not api_key_configured(
                settings.OPENAI_API_KEY
            ):
                raise ScenarioGenerationProviderError(str(exc)) from exc
            fallback_model = _fallback_openai_model()
            if not fallback_model:
                raise ScenarioGenerationProviderError(
                    "missing_scenario_generation_fallback_model"
                ) from exc
            served_model = fallback_model
            logger.warning(
                "scenario_generation_anthropic_retryable_failure_falling_back_to_openai primaryModel=%s fallbackModel=%s reason=%s",
                request.model,
                fallback_model,
                type(exc).__name__,
            )
            try:
                result = call_openai_json_schema(
                    api_key=settings.OPENAI_API_KEY,
                    model=fallback_model,
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                    response_model=ScenarioGenerationOutput,
                    timeout_seconds=settings.SCENARIO_GENERATION_TIMEOUT_SECONDS,
                    max_retries=settings.SCENARIO_GENERATION_MAX_RETRIES,
                )
            except AIProviderExecutionError as fallback_exc:
                raise ScenarioGenerationProviderError(
                    str(fallback_exc)
                ) from fallback_exc
        logger.info(
            "scenario_generation_provider_call provider=anthropic served_model=%s",
            served_model,
        )
        return ScenarioGenerationProviderResponse(
            result=result,
            model_name=served_model,
            model_version=served_model,
        )


__all__ = ["AnthropicScenarioGenerationProvider"]
