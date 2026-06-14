"""OpenAI-backed winoe-report review provider."""

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

_SUPPORTED_FALLBACK_PROVIDER = "anthropic"
_SUPPORTED_DAY_AGENT_KEY = "codeimplementationreviewer"
_SUPPORTED_AGGREGATOR_AGENT_KEY = "winoereport"

_RETRYABLE_OPENAI_ERROR_MARKERS = (
    "ratelimiterror",
    "too many requests",
    "rate limit",
    "429",
    "apitimeouterror",
    "apiconnectionerror",
    "internalservererror",
    "serviceunavailableerror",
    "overloadederror",
)


def _is_retryable_openai_error(exc: Exception) -> bool:
    parts = [type(exc).__name__, str(exc)]
    normalized = " ".join(part for part in parts if part).strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _RETRYABLE_OPENAI_ERROR_MARKERS)


def _day_timeout_seconds() -> int:
    return max(
        settings.WINOE_REPORT_DAY1_TIMEOUT_SECONDS,
        settings.WINOE_REPORT_DAY23_TIMEOUT_SECONDS,
        settings.WINOE_REPORT_DAY4_TIMEOUT_SECONDS,
        settings.WINOE_REPORT_DAY5_TIMEOUT_SECONDS,
    )


def _day_max_retries() -> int:
    return max(
        settings.WINOE_REPORT_DAY1_MAX_RETRIES,
        settings.WINOE_REPORT_DAY23_MAX_RETRIES,
        settings.WINOE_REPORT_DAY4_MAX_RETRIES,
        settings.WINOE_REPORT_DAY5_MAX_RETRIES,
    )


def _fallback_aggregator_model() -> str:
    return str(settings.WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL or "").strip()


def _normalized_provider(value: str) -> str:
    return str(value or "").strip().lower()


def _require_supported_fallback_provider(
    *, request_provider: str, operation: str
) -> None:
    normalized = _normalized_provider(request_provider)
    if normalized != _SUPPORTED_FALLBACK_PROVIDER:
        raise WinoeReportReviewProviderError(
            "unsupported_winoe_report_fallback_provider:"
            f"{operation}:openai:{request_provider}"
        )


def _fallback_day_model_for_agent(*, agent_key: str) -> str:
    normalized = _normalized_provider(agent_key)
    if normalized == _SUPPORTED_DAY_AGENT_KEY:
        return str(settings.WINOE_REPORT_DAY23_FALLBACK_MODEL or "").strip()
    raise WinoeReportReviewProviderError(
        f"unsupported_winoe_report_day_agent:{agent_key}"
    )


def _call_anthropic_with_model_fallback(
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_model,
    timeout_seconds: int,
    max_retries: int,
):
    return call_anthropic_json(
        api_key=settings.ANTHROPIC_API_KEY,
        model=model_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=response_model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


class OpenAIWinoeReportReviewProvider:
    """Run reviewer and aggregator calls via OpenAI structured outputs."""

    def review_day(
        self,
        *,
        request: WinoeReportDayReviewRequest,
    ) -> DayReviewerOutput:
        if _normalized_provider(request.agent_key) != _SUPPORTED_DAY_AGENT_KEY:
            raise WinoeReportReviewProviderError(
                f"unsupported_winoe_report_day_agent:review_day:openai:{request.agent_key}"
            )
        _require_supported_fallback_provider(
            request_provider=request.fallback_provider, operation="review_day"
        )
        served_model = request.model
        try:
            result = call_openai_json_schema(
                api_key=settings.OPENAI_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=DayReviewerOutput,
                timeout_seconds=_day_timeout_seconds(),
                max_retries=_day_max_retries(),
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_openai_error(exc) or not api_key_configured(
                settings.ANTHROPIC_API_KEY
            ):
                raise WinoeReportReviewProviderError(str(exc)) from exc
            fallback_model = _fallback_day_model_for_agent(agent_key=request.agent_key)
            if not fallback_model:
                raise WinoeReportReviewProviderError(
                    "missing_winoe_report_day23_fallback_model"
                ) from exc
            served_model = fallback_model
            logger.warning(
                "winoe_report_openai_retryable_failure_falling_back_to_anthropic operation=review_day primaryModel=%s fallbackModel=%s reason=%s",
                request.model,
                fallback_model,
                type(exc).__name__,
            )
            try:
                result = _call_anthropic_with_model_fallback(
                    model_name=fallback_model,
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                    response_model=DayReviewerOutput,
                    timeout_seconds=_day_timeout_seconds(),
                    max_retries=_day_max_retries(),
                )
            except AIProviderExecutionError as fallback_exc:
                raise WinoeReportReviewProviderError(
                    str(fallback_exc)
                ) from fallback_exc
        logger.info(
            "winoe_report_provider_call operation=review_day provider=openai served_model=%s",
            served_model,
        )
        return result

    def aggregate_winoe_report(
        self,
        *,
        request: WinoeReportAggregateRequest,
    ) -> AggregatedWinoeReportOutput:
        if _normalized_provider(request.agent_key) != _SUPPORTED_AGGREGATOR_AGENT_KEY:
            raise WinoeReportReviewProviderError(
                f"unsupported_winoe_report_agent:aggregate_winoe_report:openai:{request.agent_key}"
            )
        _require_supported_fallback_provider(
            request_provider=request.fallback_provider,
            operation="aggregate_winoe_report",
        )
        served_model = request.model
        try:
            result = call_openai_json_schema(
                api_key=settings.OPENAI_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=AggregatedWinoeReportOutput,
                timeout_seconds=settings.WINOE_REPORT_AGGREGATOR_TIMEOUT_SECONDS,
                max_retries=settings.WINOE_REPORT_AGGREGATOR_MAX_RETRIES,
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_openai_error(exc) or not api_key_configured(
                settings.ANTHROPIC_API_KEY
            ):
                raise WinoeReportReviewProviderError(str(exc)) from exc
            fallback_model = _fallback_aggregator_model()
            if not fallback_model:
                raise WinoeReportReviewProviderError(
                    "missing_winoe_report_aggregator_fallback_model"
                ) from exc
            served_model = fallback_model
            logger.warning(
                "winoe_report_openai_retryable_failure_falling_back_to_anthropic operation=aggregate_winoe_report primaryModel=%s fallbackModel=%s reason=%s",
                request.model,
                fallback_model,
                type(exc).__name__,
            )
            try:
                result = _call_anthropic_with_model_fallback(
                    model_name=fallback_model,
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
            "winoe_report_provider_call operation=aggregate_winoe_report provider=openai served_model=%s",
            served_model,
        )
        return result


__all__ = ["OpenAIWinoeReportReviewProvider"]
