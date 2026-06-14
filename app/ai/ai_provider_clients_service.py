"""Low-level SDK helpers for OpenAI and Anthropic JSON generation."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


def anthropic_api_error_summary(exc: BaseException, *, max_len: int = 400) -> str:
    """Return a single-line, non-secret summary for Anthropic HTTP/API errors."""
    parts: list[str] = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"http={status}")
    request_id = getattr(exc, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        rid = request_id.strip()
        parts.append(f"request_id={rid[:48]}")
    body = getattr(exc, "body", None)
    err_type: str | None = None
    err_msg: str | None = None
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict):
            et = nested.get("type")
            if isinstance(et, str) and et.strip():
                err_type = et.strip()[:120]
            em = nested.get("message")
            if isinstance(em, str) and em.strip():
                err_msg = " ".join(em.split())[:240]
        if err_type is None:
            bt = body.get("type")
            if isinstance(bt, str) and bt.strip():
                err_type = bt.strip()[:120]
    if err_type:
        parts.append(f"api_error_type={err_type}")
    if err_msg:
        parts.append(f"api_error_message={err_msg}")
    out = "|".join(parts)
    return out[:max_len]


class AIProviderExecutionError(RuntimeError):
    """Raised when an upstream AI provider call fails or returns invalid output."""


def api_key_configured(api_key: str | None) -> bool:
    """Return whether an API key is present and not just a placeholder."""
    normalized = (api_key or "").strip()
    return bool(normalized and normalized != "__REPLACE_ME__")


def _schema_payload(schema_model: type[BaseModel]) -> dict[str, Any]:
    return _normalize_openai_json_schema(schema_model.model_json_schema())


def _normalize_openai_json_schema(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = {
            key: _normalize_openai_json_schema(child) for key, child in value.items()
        }
        if normalized.get("type") == "object":
            normalized["additionalProperties"] = False
            properties = normalized.get("properties")
            if isinstance(properties, dict):
                normalized["required"] = list(properties.keys())
            else:
                normalized.setdefault("required", [])
        return normalized
    if isinstance(value, list):
        return [_normalize_openai_json_schema(item) for item in value]
    return value


def _extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        fenced = re.sub(r"^```(?:json)?\s*", "", text)
        fenced = re.sub(r"\s*```$", "", fenced)
        text = fenced.strip()
    return text


def openai_api_error_summary(exc: BaseException, *, max_len: int = 400) -> str:
    """Return a single-line, non-secret summary for OpenAI HTTP/API errors."""
    parts: list[str] = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"http={status}")
    request_id = getattr(exc, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        rid = request_id.strip()
        parts.append(f"request_id={rid[:48]}")
    body = getattr(exc, "body", None)
    err_type: str | None = None
    err_msg: str | None = None
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict):
            et = nested.get("type")
            if isinstance(et, str) and et.strip():
                err_type = et.strip()[:120]
            em = nested.get("message")
            if isinstance(em, str) and em.strip():
                err_msg = " ".join(em.split())[:240]
            code = nested.get("code")
            if isinstance(code, str) and code.strip():
                parts.append(f"api_error_code={code.strip()[:120]}")
        if err_type is None:
            et = body.get("type")
            if isinstance(et, str) and et.strip():
                err_type = et.strip()[:120]
        if err_msg is None:
            em = body.get("message")
            if isinstance(em, str) and em.strip():
                err_msg = " ".join(em.split())[:240]
    if err_type:
        parts.append(f"api_error_type={err_type}")
    if err_msg:
        parts.append(f"api_error_message={err_msg}")
    out = "|".join(parts)
    return out[:max_len]


def _openai_schema_validation_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "invalid_json_schema" in message
        or "Invalid schema for response_format" in message
    )


def _normalized_openai_reasoning(reasoning_effort: str | None) -> dict[str, str] | None:
    normalized = (reasoning_effort or "").strip().lower()
    if normalized == "minimal":
        normalized = "none"
    if normalized in {"none", "low", "medium", "high", "xhigh"}:
        return {"effort": normalized}
    return None


def _normalized_openai_text_verbosity(text_verbosity: str | None) -> str | None:
    normalized = (text_verbosity or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return None


def _call_openai_prompt_json(
    *,
    client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    text_verbosity: str | None = None,
    temperature: float | None = None,
) -> BaseModel:
    schema_json = json.dumps(response_model.model_json_schema(), sort_keys=True)
    prompt_text = (
        f"{system_prompt.strip()}\n\n"
        "Return only one JSON object that matches this schema exactly.\n"
        f"{schema_json}"
    )
    request_kwargs: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": prompt_text}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
    }
    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
        request_kwargs["max_output_tokens"] = max_output_tokens
    reasoning = _normalized_openai_reasoning(reasoning_effort)
    if reasoning is not None:
        request_kwargs["reasoning"] = reasoning
    verbosity = _normalized_openai_text_verbosity(text_verbosity)
    if verbosity is not None:
        request_kwargs["text"] = {"verbosity": verbosity}
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    response = client.responses.create(
        **request_kwargs,
    )
    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise AIProviderExecutionError("openai_empty_structured_output")
    try:
        parsed = json.loads(_extract_json_text(output_text))
    except Exception as exc:
        raise AIProviderExecutionError("openai_invalid_structured_output") from exc
    try:
        return response_model.model_validate(parsed)
    except Exception as exc:
        raise AIProviderExecutionError("openai_invalid_structured_output") from exc


def call_openai_json_schema(
    *,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    timeout_seconds: int,
    max_retries: int,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    text_verbosity: str | None = None,
    temperature: float | None = None,
) -> BaseModel:
    """Call OpenAI Responses API with strict JSON-schema output."""
    if not api_key_configured(api_key):
        raise AIProviderExecutionError("missing_openai_api_key")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AIProviderExecutionError("openai_sdk_not_installed") from exc

    client = OpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
    request_kwargs: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": response_model.__name__,
                "schema": _schema_payload(response_model),
                "strict": True,
            }
        },
    }
    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
        request_kwargs["max_output_tokens"] = max_output_tokens
    reasoning = _normalized_openai_reasoning(reasoning_effort)
    if reasoning is not None:
        request_kwargs["reasoning"] = reasoning
    verbosity = _normalized_openai_text_verbosity(text_verbosity)
    if verbosity is not None:
        request_kwargs["text"]["verbosity"] = verbosity
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    try:
        response = client.responses.create(**request_kwargs)
    except Exception as exc:  # pragma: no cover - network/provider variability
        if _openai_schema_validation_error(exc):
            try:
                return _call_openai_prompt_json(
                    client=client,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=response_model,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort=reasoning_effort,
                    text_verbosity=text_verbosity,
                    temperature=temperature,
                )
            except AIProviderExecutionError:
                raise
            except Exception as fallback_exc:
                raise AIProviderExecutionError(
                    f"openai_request_failed:{openai_api_error_summary(fallback_exc)}"
                ) from fallback_exc
        raise AIProviderExecutionError(
            f"openai_request_failed:{openai_api_error_summary(exc)}"
        ) from exc

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise AIProviderExecutionError("openai_empty_structured_output")
    try:
        return response_model.model_validate_json(output_text)
    except Exception as exc:
        raise AIProviderExecutionError("openai_invalid_structured_output") from exc


def call_anthropic_json(
    *,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    timeout_seconds: int,
    max_retries: int,
    max_tokens: int = 4_096,
) -> BaseModel:
    """Call Anthropic Messages API and validate JSON output against a schema."""
    if not api_key_configured(api_key):
        raise AIProviderExecutionError("missing_anthropic_api_key")
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AIProviderExecutionError("anthropic_sdk_not_installed") from exc

    tool_schema = _schema_payload(response_model)
    schema_json = json.dumps(tool_schema, sort_keys=True)
    system_text = (
        f"{system_prompt.strip()}\n\n"
        "Return only one JSON object that matches this schema exactly.\n"
        f"{schema_json}"
    )
    client = Anthropic(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
    # Prefer plain JSON-in-system first. Tool-use with large nested JSON Schemas
    # (for example scenario generation) can return 400 from the provider even when
    # the same contract succeeds via natural-language JSON instructions.
    primary_exc: BaseException | None = None
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_text,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc_plain:
        primary_exc = exc_plain
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt.strip(),
                tools=[
                    {
                        "name": response_model.__name__,
                        "description": "Return the structured response payload.",
                        "input_schema": tool_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": response_model.__name__},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as tool_exc:  # pragma: no cover - network/provider variability
            tool_summary = anthropic_api_error_summary(tool_exc)
            prior = (
                anthropic_api_error_summary(primary_exc)
                if primary_exc is not None
                else "none"
            )
            raise AIProviderExecutionError(
                "anthropic_request_failed:"
                f"{type(tool_exc).__name__}|tool_attempt={tool_summary}|json_prompt_attempt={prior}"
            ) from tool_exc

    blocks = getattr(response, "content", [])
    for block in blocks:
        if getattr(block, "type", None) != "tool_use":
            continue
        payload = getattr(block, "input", None)
        try:
            return response_model.model_validate(payload)
        except Exception as exc:
            raise AIProviderExecutionError("anthropic_invalid_json_output") from exc

    text_parts = [
        getattr(block, "text", "")
        for block in blocks
        if getattr(block, "type", None) == "text"
    ]
    payload_text = _extract_json_text("\n".join(part for part in text_parts if part))
    if not payload_text:
        raise AIProviderExecutionError("anthropic_empty_json_output")
    try:
        return response_model.model_validate(json.loads(payload_text))
    except Exception as exc:
        raise AIProviderExecutionError("anthropic_invalid_json_output") from exc


__all__ = [
    "AIProviderExecutionError",
    "_openai_schema_validation_error",
    "anthropic_api_error_summary",
    "api_key_configured",
    "call_anthropic_json",
    "call_openai_json_schema",
    "openai_api_error_summary",
]
