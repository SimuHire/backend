"""Anthropic-backed winoe-report review provider."""

from __future__ import annotations

import logging

from app.ai import AggregatedWinoeReportOutput, DayReviewerOutput
from app.ai.ai_provider_clients_service import (
    AIProviderExecutionError,
    api_key_configured,
    call_anthropic_json,
    call_openai_json_schema,
)
from app.config import settings
from app.integrations.winoe_report_review.base_client import (
    WinoeReportAggregateRequest,
    WinoeReportDayReviewRequest,
    WinoeReportReviewProviderError,
)

logger = logging.getLogger(__name__)

_SUPPORTED_FALLBACK_PROVIDER = "openai"
_SUPPORTED_DAY_AGENT_KEYS = {
    "designdocreviewer",
    "demopresentationreviewer",
    "reflectionessayreviewer",
}


def _normalized_provider(value: str) -> str:
    return str(value or "").strip().lower()


def _require_supported_fallback_provider(
    *, request_provider: str, operation: str
) -> None:
    normalized = _normalized_provider(request_provider)
    if normalized != _SUPPORTED_FALLBACK_PROVIDER:
        raise WinoeReportReviewProviderError(
            "unsupported_winoe_report_fallback_provider:"
            f"{operation}:anthropic:{request_provider}"
        )


def _require_supported_day_agent(*, agent_key: str, operation: str) -> None:
    normalized = _normalized_provider(agent_key)
    if normalized not in _SUPPORTED_DAY_AGENT_KEYS:
        raise WinoeReportReviewProviderError(
            f"unsupported_winoe_report_day_agent:{operation}:anthropic:{agent_key}"
        )


def _fallback_day_openai_model(*, agent_key: str) -> str:
    normalized = _normalized_provider(agent_key)
    if normalized == "designdocreviewer":
        return str(settings.WINOE_REPORT_DAY1_FALLBACK_MODEL or "").strip()
    if normalized == "demopresentationreviewer":
        return str(settings.WINOE_REPORT_DAY4_FALLBACK_MODEL or "").strip()
    if normalized == "reflectionessayreviewer":
        return str(settings.WINOE_REPORT_DAY5_FALLBACK_MODEL or "").strip()
    raise WinoeReportReviewProviderError(
        f"unsupported_winoe_report_day_agent:{agent_key}"
    )


def _fallback_aggregator_openai_model() -> str:
    return str(settings.WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL or "").strip()


def _is_retryable_anthropic_error(exc: Exception) -> bool:
    normalized = str(exc).strip().lower()
    if not normalized:
        return False
    return normalized.startswith("anthropic_request_failed") or normalized.startswith(
        "anthropic_invalid_json_output"
    )


class AnthropicWinoeReportReviewProvider:
    """Run reviewer and aggregator calls via Anthropic JSON outputs."""

    def review_day(
        self,
        *,
        request: WinoeReportDayReviewRequest,
    ) -> DayReviewerOutput:
        _require_supported_day_agent(
            agent_key=request.agent_key, operation="review_day"
        )
        _require_supported_fallback_provider(
            request_provider=request.fallback_provider, operation="review_day"
        )
        served_model = request.model
        try:
            result = call_anthropic_json(
                api_key=settings.ANTHROPIC_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=DayReviewerOutput,
                timeout_seconds=max(
                    settings.WINOE_REPORT_DAY1_TIMEOUT_SECONDS,
                    settings.WINOE_REPORT_DAY23_TIMEOUT_SECONDS,
                    settings.WINOE_REPORT_DAY4_TIMEOUT_SECONDS,
                    settings.WINOE_REPORT_DAY5_TIMEOUT_SECONDS,
                ),
                max_retries=max(
                    settings.WINOE_REPORT_DAY1_MAX_RETRIES,
                    settings.WINOE_REPORT_DAY23_MAX_RETRIES,
                    settings.WINOE_REPORT_DAY4_MAX_RETRIES,
                    settings.WINOE_REPORT_DAY5_MAX_RETRIES,
                ),
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_anthropic_error(exc) or not api_key_configured(
                settings.OPENAI_API_KEY
            ):
                raise WinoeReportReviewProviderError(str(exc)) from exc
            fallback_model = _fallback_day_openai_model(agent_key=request.agent_key)
            if not fallback_model:
                raise WinoeReportReviewProviderError(
                    "missing_winoe_report_day_fallback_model"
                ) from exc
            served_model = fallback_model
            logger.warning(
                "winoe_report_anthropic_retryable_failure_falling_back_to_openai operation=review_day primaryModel=%s fallbackModel=%s reason=%s",
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
                    response_model=DayReviewerOutput,
                    timeout_seconds=max(
                        settings.WINOE_REPORT_DAY1_TIMEOUT_SECONDS,
                        settings.WINOE_REPORT_DAY23_TIMEOUT_SECONDS,
                        settings.WINOE_REPORT_DAY4_TIMEOUT_SECONDS,
                        settings.WINOE_REPORT_DAY5_TIMEOUT_SECONDS,
                    ),
                    max_retries=max(
                        settings.WINOE_REPORT_DAY1_MAX_RETRIES,
                        settings.WINOE_REPORT_DAY23_MAX_RETRIES,
                        settings.WINOE_REPORT_DAY4_MAX_RETRIES,
                        settings.WINOE_REPORT_DAY5_MAX_RETRIES,
                    ),
                )
            except AIProviderExecutionError as fallback_exc:
                raise WinoeReportReviewProviderError(
                    str(fallback_exc)
                ) from fallback_exc
        logger.info(
            "winoe_report_provider_call operation=review_day provider=anthropic served_model=%s",
            served_model,
        )
        return result

    def aggregate_winoe_report(
        self,
        *,
        request: WinoeReportAggregateRequest,
    ) -> AggregatedWinoeReportOutput:
        if _normalized_provider(request.agent_key) != "winoereport":
            raise WinoeReportReviewProviderError(
                f"unsupported_winoe_report_agent:aggregate_winoe_report:anthropic:{request.agent_key}"
            )
        _require_supported_fallback_provider(
            request_provider=request.fallback_provider,
            operation="aggregate_winoe_report",
        )
        served_model = request.model
        try:
            result = call_anthropic_json(
                api_key=settings.ANTHROPIC_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=AggregatedWinoeReportOutput,
                timeout_seconds=settings.WINOE_REPORT_AGGREGATOR_TIMEOUT_SECONDS,
                max_retries=settings.WINOE_REPORT_AGGREGATOR_MAX_RETRIES,
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_anthropic_error(exc) or not api_key_configured(
                settings.OPENAI_API_KEY
            ):
                raise WinoeReportReviewProviderError(str(exc)) from exc
            fallback_model = _fallback_aggregator_openai_model()
            if not fallback_model:
                raise WinoeReportReviewProviderError(
                    "missing_winoe_report_aggregator_fallback_model"
                ) from exc
            served_model = fallback_model
            logger.warning(
                "winoe_report_anthropic_retryable_failure_falling_back_to_openai operation=aggregate_winoe_report primaryModel=%s fallbackModel=%s reason=%s",
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
                    response_model=AggregatedWinoeReportOutput,
                    timeout_seconds=settings.WINOE_REPORT_AGGREGATOR_TIMEOUT_SECONDS,
                    max_retries=settings.WINOE_REPORT_AGGREGATOR_MAX_RETRIES,
                )
            except AIProviderExecutionError as fallback_exc:
                raise WinoeReportReviewProviderError(
                    str(fallback_exc)
                ) from fallback_exc
        logger.info(
            "winoe_report_provider_call operation=aggregate_winoe_report provider=anthropic served_model=%s",
            served_model,
        )
        return result


__all__ = ["AnthropicWinoeReportReviewProvider"]
