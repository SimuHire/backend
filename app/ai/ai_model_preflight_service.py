"""Model matrix and preflight checks for Winoe AI demo safety."""

from __future__ import annotations

import io
import json
import tempfile
import wave
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel

from app.ai.ai_prompt_pack_service import build_prompt_pack_entry
from app.ai.ai_provider_clients_service import (
    AIProviderExecutionError,
    api_key_configured,
    call_anthropic_json,
    call_openai_json_schema,
    openai_api_error_summary,
)
from app.config import settings

AIModelCapability = Literal["structured_json", "transcription"]


@dataclass(frozen=True, slots=True)
class AIModelMatrixRow:
    """Describe one feature-level primary or fallback model binding."""

    feature: str
    role: str
    capability: AIModelCapability
    provider: str
    model: str
    prompt_version: str
    configured_from: str


@dataclass(frozen=True, slots=True)
class AIModelPreflightTarget:
    """Describe one distinct provider/model pair to verify."""

    capability: AIModelCapability
    provider: str
    model: str
    used_by: tuple[AIModelMatrixRow, ...]


@dataclass(frozen=True, slots=True)
class AIModelPreflightResult:
    """Describe one live model reachability check."""

    capability: AIModelCapability
    provider: str
    model: str
    reachable: bool
    used_by: tuple[str, ...]
    error: str | None = None


class _ModelPreflightProbeOutput(BaseModel):
    ok: bool


def _settings_path(*parts: str) -> str:
    if len(parts) == 2:
        return f"app/config/config_settings_fields_config.py:L{parts[0]}-L{parts[1]}"
    return "app/config/config_settings_fields_config.py:" + ",".join(parts)


def _require_non_blank(*, feature: str, role: str, value: str, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    raise AIProviderExecutionError(
        f"missing_model_config:{feature}:{role}:{field_name}"
    )


def _require_supported_fallback_provider(
    *,
    feature: str,
    field_name: str,
    value: str,
    expected_provider: str,
) -> str:
    normalized = value.strip().lower()
    expected = expected_provider.strip().lower()
    if normalized == expected:
        return normalized
    raise AIProviderExecutionError(
        f"unsupported_fallback_provider:{feature}:{field_name}:{value}:{expected_provider}"
    )


def build_ai_model_matrix_rows() -> list[AIModelMatrixRow]:
    """Return the pinned primary/fallback model matrix used in the demo."""
    prestart_prompt_version = build_prompt_pack_entry("prestart").prompt_version
    day1_prompt_version = build_prompt_pack_entry("designDocReviewer").prompt_version
    day23_prompt_version = build_prompt_pack_entry(
        "codeImplementationReviewer"
    ).prompt_version
    day4_prompt_version = build_prompt_pack_entry(
        "demoPresentationReviewer"
    ).prompt_version
    day5_prompt_version = build_prompt_pack_entry(
        "reflectionEssayReviewer"
    ).prompt_version
    winoe_prompt_version = build_prompt_pack_entry("winoeReport").prompt_version

    return [
        AIModelMatrixRow(
            feature="Prestart / Project Brief Creator",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Prestart / Project Brief Creator",
                role="primary",
                field_name="SCENARIO_GENERATION_PROVIDER",
                value=str(settings.SCENARIO_GENERATION_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Prestart / Project Brief Creator",
                role="primary",
                field_name="SCENARIO_GENERATION_MODEL",
                value=str(settings.SCENARIO_GENERATION_MODEL or ""),
            ),
            prompt_version=prestart_prompt_version,
            configured_from=_settings_path("93", "96"),
        ),
        AIModelMatrixRow(
            feature="Prestart / Project Brief Creator",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Prestart / Project Brief Creator",
                field_name="SCENARIO_GENERATION_FALLBACK_PROVIDER",
                value=str(settings.SCENARIO_GENERATION_FALLBACK_PROVIDER or ""),
                expected_provider="openai",
            ).lower(),
            model=_require_non_blank(
                feature="Prestart / Project Brief Creator",
                role="fallback",
                field_name="SCENARIO_GENERATION_FALLBACK_MODEL",
                value=str(settings.SCENARIO_GENERATION_FALLBACK_MODEL or ""),
            ),
            prompt_version=prestart_prompt_version,
            configured_from="app/integrations/scenario_generation/anthropic_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Design Doc Reviewer",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Design Doc Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY1_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY1_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Design Doc Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY1_MODEL",
                value=str(settings.WINOE_REPORT_DAY1_MODEL or ""),
            ),
            prompt_version=day1_prompt_version,
            configured_from=_settings_path("98", "101"),
        ),
        AIModelMatrixRow(
            feature="Design Doc Reviewer",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Design Doc Reviewer",
                field_name="WINOE_REPORT_DAY1_FALLBACK_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY1_FALLBACK_PROVIDER or ""),
                expected_provider="openai",
            ).lower(),
            model=_require_non_blank(
                feature="Design Doc Reviewer",
                role="fallback",
                field_name="WINOE_REPORT_DAY1_FALLBACK_MODEL",
                value=str(settings.WINOE_REPORT_DAY1_FALLBACK_MODEL or ""),
            ),
            prompt_version=day1_prompt_version,
            configured_from="app/integrations/winoe_report_review/anthropic_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Code Implementation Reviewer",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Code Implementation Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY23_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY23_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Code Implementation Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY23_MODEL",
                value=str(settings.WINOE_REPORT_DAY23_MODEL or ""),
            ),
            prompt_version=day23_prompt_version,
            configured_from=_settings_path("103", "106"),
        ),
        AIModelMatrixRow(
            feature="Code Implementation Reviewer",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Code Implementation Reviewer",
                field_name="WINOE_REPORT_DAY23_FALLBACK_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY23_FALLBACK_PROVIDER or ""),
                expected_provider="anthropic",
            ).lower(),
            model=_require_non_blank(
                feature="Code Implementation Reviewer",
                role="fallback",
                field_name="WINOE_REPORT_DAY23_FALLBACK_MODEL",
                value=str(settings.WINOE_REPORT_DAY23_FALLBACK_MODEL or ""),
            ),
            prompt_version=day23_prompt_version,
            configured_from="app/integrations/winoe_report_review/openai_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Demo Presentation Reviewer",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Demo Presentation Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY4_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY4_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Demo Presentation Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY4_MODEL",
                value=str(settings.WINOE_REPORT_DAY4_MODEL or ""),
            ),
            prompt_version=day4_prompt_version,
            configured_from=_settings_path("108", "111"),
        ),
        AIModelMatrixRow(
            feature="Demo Presentation Reviewer",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Demo Presentation Reviewer",
                field_name="WINOE_REPORT_DAY4_FALLBACK_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY4_FALLBACK_PROVIDER or ""),
                expected_provider="openai",
            ).lower(),
            model=_require_non_blank(
                feature="Demo Presentation Reviewer",
                role="fallback",
                field_name="WINOE_REPORT_DAY4_FALLBACK_MODEL",
                value=str(settings.WINOE_REPORT_DAY4_FALLBACK_MODEL or ""),
            ),
            prompt_version=day4_prompt_version,
            configured_from="app/integrations/winoe_report_review/anthropic_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Reflection Essay Reviewer",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Reflection Essay Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY5_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY5_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Reflection Essay Reviewer",
                role="primary",
                field_name="WINOE_REPORT_DAY5_MODEL",
                value=str(settings.WINOE_REPORT_DAY5_MODEL or ""),
            ),
            prompt_version=day5_prompt_version,
            configured_from=_settings_path("113", "116"),
        ),
        AIModelMatrixRow(
            feature="Reflection Essay Reviewer",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Reflection Essay Reviewer",
                field_name="WINOE_REPORT_DAY5_FALLBACK_PROVIDER",
                value=str(settings.WINOE_REPORT_DAY5_FALLBACK_PROVIDER or ""),
                expected_provider="openai",
            ).lower(),
            model=_require_non_blank(
                feature="Reflection Essay Reviewer",
                role="fallback",
                field_name="WINOE_REPORT_DAY5_FALLBACK_MODEL",
                value=str(settings.WINOE_REPORT_DAY5_FALLBACK_MODEL or ""),
            ),
            prompt_version=day5_prompt_version,
            configured_from="app/integrations/winoe_report_review/anthropic_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Winoe, the Talent Intelligence Agent",
            role="primary",
            capability="structured_json",
            provider=_require_non_blank(
                feature="Winoe, the Talent Intelligence Agent",
                role="primary",
                field_name="WINOE_REPORT_AGGREGATOR_PROVIDER",
                value=str(settings.WINOE_REPORT_AGGREGATOR_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Winoe, the Talent Intelligence Agent",
                role="primary",
                field_name="WINOE_REPORT_AGGREGATOR_MODEL",
                value=str(settings.WINOE_REPORT_AGGREGATOR_MODEL or ""),
            ),
            prompt_version=winoe_prompt_version,
            configured_from=_settings_path("118", "121"),
        ),
        AIModelMatrixRow(
            feature="Winoe, the Talent Intelligence Agent",
            role="fallback",
            capability="structured_json",
            provider=_require_supported_fallback_provider(
                feature="Winoe, the Talent Intelligence Agent",
                field_name="WINOE_REPORT_AGGREGATOR_FALLBACK_PROVIDER",
                value=str(settings.WINOE_REPORT_AGGREGATOR_FALLBACK_PROVIDER or ""),
                expected_provider="anthropic",
            ).lower(),
            model=_require_non_blank(
                feature="Winoe, the Talent Intelligence Agent",
                role="fallback",
                field_name="WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL",
                value=str(settings.WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL or ""),
            ),
            prompt_version=winoe_prompt_version,
            configured_from="app/integrations/winoe_report_review/openai_provider_client.py",
        ),
        AIModelMatrixRow(
            feature="Transcription",
            role="primary",
            capability="transcription",
            provider=_require_non_blank(
                feature="Transcription",
                role="primary",
                field_name="TRANSCRIPTION_PROVIDER",
                value=str(settings.TRANSCRIPTION_PROVIDER or ""),
            ).lower(),
            model=_require_non_blank(
                feature="Transcription",
                role="primary",
                field_name="TRANSCRIPTION_MODEL",
                value=str(settings.TRANSCRIPTION_MODEL or ""),
            ),
            prompt_version="n/a",
            configured_from=_settings_path("123", "126"),
        ),
    ]


def build_ai_model_preflight_targets() -> list[AIModelPreflightTarget]:
    """Collapse the matrix into distinct provider/model checks."""
    rows = build_ai_model_matrix_rows()
    grouped: dict[tuple[AIModelCapability, str, str], list[AIModelMatrixRow]] = {}
    for row in rows:
        key = (row.capability, row.provider, row.model)
        grouped.setdefault(key, []).append(row)
    return [
        AIModelPreflightTarget(
            capability=capability,
            provider=provider,
            model=model,
            used_by=tuple(used_by),
        )
        for (capability, provider, model), used_by in sorted(grouped.items())
        if provider and model
    ]


def _build_silent_wav_bytes(*, duration_seconds: float = 0.25) -> bytes:
    """Create a tiny deterministic silent WAV fixture for transcription preflight."""
    sample_rate = 16_000
    frame_count = max(1, int(sample_rate * duration_seconds))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def _openai_model_reachable(*, model: str) -> None:
    if not api_key_configured(settings.OPENAI_API_KEY):
        raise AIProviderExecutionError("missing_openai_api_key")
    call_openai_json_schema(
        api_key=settings.OPENAI_API_KEY,
        model=model,
        system_prompt="Return a JSON object that confirms structured output support.",
        user_prompt='Respond with {"ok": true}.',
        response_model=_ModelPreflightProbeOutput,
        timeout_seconds=20,
        max_retries=0,
        max_output_tokens=16,
    )


def _openai_transcription_model_reachable(*, model: str) -> None:
    if not api_key_configured(settings.OPENAI_API_KEY):
        raise AIProviderExecutionError("missing_openai_api_key")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AIProviderExecutionError("openai_sdk_not_installed") from exc

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=20,
        max_retries=0,
    )
    audio_bytes = _build_silent_wav_bytes()
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(audio_bytes)
        handle.flush()
        try:
            with open(handle.name, "rb") as audio_file:
                client.audio.transcriptions.create(
                    file=audio_file,
                    model=model,
                    response_format="json",
                )
        except Exception as exc:  # pragma: no cover - exercised by negative tests
            raise AIProviderExecutionError(
                f"openai_transcription_failed:{openai_api_error_summary(exc)}"
            ) from exc


def _anthropic_model_reachable(*, model: str) -> None:
    if not api_key_configured(settings.ANTHROPIC_API_KEY):
        raise AIProviderExecutionError("missing_anthropic_api_key")
    call_anthropic_json(
        api_key=settings.ANTHROPIC_API_KEY,
        model=model,
        system_prompt="Return a JSON object that confirms message-based structured output support.",
        user_prompt='Respond with {"ok": true}.',
        response_model=_ModelPreflightProbeOutput,
        timeout_seconds=20,
        max_retries=0,
        max_tokens=8,
    )


def verify_ai_model_endpoint(*, provider: str, model: str) -> None:
    """Raise if one configured endpoint is not reachable."""
    normalized = (provider or "").strip().lower()
    if normalized == "openai":
        target = next(
            (
                row
                for row in build_ai_model_matrix_rows()
                if row.provider == normalized and row.model == model
            ),
            None,
        )
        if target is None:
            raise AIProviderExecutionError(f"unknown_model_target:{provider}:{model}")
        if target.capability == "structured_json":
            _openai_model_reachable(model=model)
            return
        if target.capability == "transcription":
            _openai_transcription_model_reachable(model=model)
            return
        raise AIProviderExecutionError(
            f"unsupported_probe_capability:{provider}:{model}:{target.capability}"
        )
        return
    if normalized == "anthropic":
        _anthropic_model_reachable(model=model)
        return
    raise AIProviderExecutionError(f"unsupported_provider:{provider}")


def verify_ai_model_preflight() -> list[AIModelPreflightResult]:
    """Verify every distinct configured endpoint and return the results."""
    results: list[AIModelPreflightResult] = []
    failures: list[str] = []
    for target in build_ai_model_preflight_targets():
        used_by = tuple(
            f"{row.feature}:{row.role}:{row.prompt_version}" for row in target.used_by
        )
        try:
            verify_ai_model_endpoint(provider=target.provider, model=target.model)
        except Exception as exc:  # pragma: no cover - exercised by negative tests
            message = (
                f"{target.provider}:{target.model}:{target.capability}:"
                f"{type(exc).__name__}"
            )
            failure_detail = str(exc).strip()
            if failure_detail:
                message = f"{message}:{failure_detail}"
            failures.append(message)
            results.append(
                AIModelPreflightResult(
                    capability=target.capability,
                    provider=target.provider,
                    model=target.model,
                    reachable=False,
                    used_by=used_by,
                    error=message,
                )
            )
        else:
            results.append(
                AIModelPreflightResult(
                    capability=target.capability,
                    provider=target.provider,
                    model=target.model,
                    reachable=True,
                    used_by=used_by,
                )
            )
    if failures:
        raise RuntimeError(
            "model_preflight_failed\n"
            + json.dumps(
                {
                    "failures": failures,
                    "results": [asdict(result) for result in results],
                },
                indent=2,
                sort_keys=True,
            )
        )
    return results


__all__ = [
    "AIModelMatrixRow",
    "AIModelCapability",
    "AIModelPreflightResult",
    "AIModelPreflightTarget",
    "build_ai_model_matrix_rows",
    "build_ai_model_preflight_targets",
    "verify_ai_model_endpoint",
    "verify_ai_model_preflight",
]
