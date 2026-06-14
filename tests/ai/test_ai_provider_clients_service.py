from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.ai import ai_provider_clients_service as provider_clients


class DemoOutput(BaseModel):
    value: str


class StrictOutput(BaseModel):
    value: int


def test_provider_client_helper_functions_cover_normalization_and_validation() -> None:
    assert provider_clients.api_key_configured("key")
    assert not provider_clients.api_key_configured(None)
    assert not provider_clients.api_key_configured("__REPLACE_ME__")

    assert provider_clients._openai_schema_validation_error(
        RuntimeError("Invalid schema for response_format")
    )
    assert provider_clients._openai_schema_validation_error(
        RuntimeError("invalid_json_schema")
    )
    assert not provider_clients._openai_schema_validation_error(RuntimeError("other"))

    assert provider_clients._extract_json_text('```json\n{"value":"x"}\n```') == (
        '{"value":"x"}'
    )
    assert provider_clients._extract_json_text('  {"value":"x"}  ') == ('{"value":"x"}')

    assert provider_clients._normalized_openai_reasoning("minimal") == {
        "effort": "none"
    }
    assert provider_clients._normalized_openai_reasoning("high") == {"effort": "high"}
    assert provider_clients._normalized_openai_reasoning("invalid") is None
    assert provider_clients._normalized_openai_text_verbosity("medium") == "medium"
    assert provider_clients._normalized_openai_text_verbosity("invalid") is None
    assert provider_clients._normalize_openai_json_schema({"type": "object"}) == {
        "type": "object",
        "additionalProperties": False,
        "required": [],
    }


def test_call_openai_prompt_json_accepts_fenced_json_and_applies_request_options() -> (
    None
):
    captured: dict[str, object] = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='```json\n{"value":"ok"}\n```')

    result = provider_clients._call_openai_prompt_json(
        client=SimpleNamespace(responses=_FakeResponses()),
        model="gpt-4.1",
        system_prompt="system",
        user_prompt="user",
        response_model=DemoOutput,
        max_output_tokens=256,
        reasoning_effort="minimal",
        text_verbosity="high",
        temperature=0.2,
    )

    assert result.value == "ok"
    assert captured["model"] == "gpt-4.1"
    assert captured["max_output_tokens"] == 256
    assert captured["reasoning"] == {"effort": "none"}
    assert captured["text"] == {"verbosity": "high"}
    assert captured["temperature"] == 0.2


def test_call_openai_prompt_json_rejects_empty_and_invalid_output() -> None:
    class _EmptyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text=" ")

    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_empty_structured_output",
    ):
        provider_clients._call_openai_prompt_json(
            client=SimpleNamespace(responses=_EmptyResponses()),
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
        )

    class _InvalidResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text="{not-json}")

    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_invalid_structured_output",
    ):
        provider_clients._call_openai_prompt_json(
            client=SimpleNamespace(responses=_InvalidResponses()),
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
        )

    class _InvalidModelResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text='{"value":"not-an-int"}')

    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_invalid_structured_output",
    ):
        provider_clients._call_openai_prompt_json(
            client=SimpleNamespace(responses=_InvalidModelResponses()),
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=StrictOutput,
        )


def test_call_openai_json_schema_falls_back_after_schema_validation_error(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeResponses:
        def __init__(self):
            self._count = 0

        def create(self, **kwargs):
            self._count += 1
            calls.append(kwargs)
            if self._count == 1:
                raise RuntimeError("Invalid schema for response_format")
            return SimpleNamespace(output_text='{"value":"fallback"}')

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = provider_clients.call_openai_json_schema(
        api_key="key",
        model="gpt-4.1",
        system_prompt=" system ",
        user_prompt=" user ",
        response_model=DemoOutput,
        timeout_seconds=10,
        max_retries=2,
        max_output_tokens=128,
        reasoning_effort="minimal",
        text_verbosity="low",
        temperature=0.1,
    )

    assert result.value == "fallback"
    assert len(calls) == 2
    assert calls[0]["text"]["format"]["strict"] is True
    assert calls[1]["reasoning"] == {"effort": "none"}
    assert calls[1]["text"] == {"verbosity": "low"}


def test_call_openai_json_schema_reports_request_failure(monkeypatch) -> None:
    class _FakeResponses:
        def create(self, **_kwargs):
            raise RuntimeError("boom")

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_request_failed:RuntimeError",
    ):
        provider_clients.call_openai_json_schema(
            api_key="key",
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_call_openai_json_schema_reports_missing_sdk(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)

    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_sdk_not_installed",
    ):
        provider_clients.call_openai_json_schema(
            api_key="key",
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_call_openai_json_schema_rejects_missing_api_key() -> None:
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="missing_openai_api_key",
    ):
        provider_clients.call_openai_json_schema(
            api_key="__REPLACE_ME__",
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_call_anthropic_json_covers_tool_and_text_paths(monkeypatch) -> None:
    class _ToolResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", input={"value": "tool"})]
            )

    class _TextResponses:
        def __init__(self):
            self._count = 0

        def create(self, **kwargs):
            self._count += 1
            if self._count == 1:
                raise RuntimeError("temporary")
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text='```json\n{"value":"text"}\n```')
                ]
            )

    class _FakeAnthropicTool:
        def __init__(self, **_kwargs):
            self.messages = _ToolResponses()

    class _FakeAnthropicText:
        def __init__(self, **_kwargs):
            self.messages = _TextResponses()

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropicTool)
    )
    tool_result = provider_clients.call_anthropic_json(
        api_key="key",
        model="claude-3",
        system_prompt=" system ",
        user_prompt=" user ",
        response_model=DemoOutput,
        timeout_seconds=10,
        max_retries=2,
    )
    assert tool_result.value == "tool"

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropicText)
    )
    text_result = provider_clients.call_anthropic_json(
        api_key="key",
        model="claude-3",
        system_prompt=" system ",
        user_prompt=" user ",
        response_model=DemoOutput,
        timeout_seconds=10,
        max_retries=2,
    )
    assert text_result.value == "text"


def test_call_anthropic_json_reports_validation_and_sdk_errors(monkeypatch) -> None:
    class _BadToolResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", input={"value": "not-int"})]
            )

    class _BadTextResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=" ")])

    class _FakeAnthropicBadTool:
        def __init__(self, **_kwargs):
            self.messages = _BadToolResponses()

    class _FakeAnthropicBadText:
        def __init__(self, **_kwargs):
            self.messages = _BadTextResponses()

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropicBadTool)
    )
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="anthropic_invalid_json_output",
    ):
        provider_clients.call_anthropic_json(
            api_key="key",
            model="claude-3",
            system_prompt="system",
            user_prompt="user",
            response_model=StrictOutput,
            timeout_seconds=10,
            max_retries=2,
        )

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropicBadText)
    )
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="anthropic_empty_json_output",
    ):
        provider_clients.call_anthropic_json(
            api_key="key",
            model="claude-3",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )

    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="anthropic_sdk_not_installed",
    ):
        provider_clients.call_anthropic_json(
            api_key="key",
            model="claude-3",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_call_anthropic_json_rejects_missing_api_key() -> None:
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="missing_anthropic_api_key",
    ):
        provider_clients.call_anthropic_json(
            api_key="__REPLACE_ME__",
            model="claude-3",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_call_openai_json_schema_and_anthropic_json_cover_remaining_branches(
    monkeypatch,
) -> None:
    summary = provider_clients.anthropic_api_error_summary(
        SimpleNamespace(
            status_code=429,
            request_id=" req-123 ",
            body={
                "error": {
                    "type": "rate_limit_error",
                    "message": " too many\nrequests ",
                }
            },
        )
    )
    assert "http=429" in summary
    assert "request_id=req-123" in summary
    assert "api_error_type=rate_limit_error" in summary
    assert "api_error_message=too many requests" in summary

    class _EmptyOpenAIResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text=" ")

    class _InvalidOpenAIResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text='{"value":"not-an-int"}')

    class _FakeOpenAIEmpty:
        def __init__(self, **_kwargs):
            self.responses = _EmptyOpenAIResponses()

    class _FakeOpenAIInvalid:
        def __init__(self, **_kwargs):
            self.responses = _InvalidOpenAIResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAIEmpty))
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_empty_structured_output",
    ):
        provider_clients.call_openai_json_schema(
            api_key="key",
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=_FakeOpenAIInvalid),
    )
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="openai_invalid_structured_output",
    ):
        provider_clients.call_openai_json_schema(
            api_key="key",
            model="gpt-4.1",
            system_prompt="system",
            user_prompt="user",
            response_model=StrictOutput,
            timeout_seconds=10,
            max_retries=2,
        )

    class _FakeAnthropicMessages:
        def create(self, **_kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not-json")]
            )

    class _FakeAnthropic:
        def __init__(self, **_kwargs):
            self.messages = _FakeAnthropicMessages()

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=_FakeAnthropic),
    )
    with pytest.raises(
        provider_clients.AIProviderExecutionError,
        match="anthropic_invalid_json_output",
    ):
        provider_clients.call_anthropic_json(
            api_key="key",
            model="claude-3.5",
            system_prompt="system",
            user_prompt="user",
            response_model=DemoOutput,
            timeout_seconds=10,
            max_retries=2,
        )


def test_anthropic_api_error_summary_covers_body_type_fallback_branch() -> None:
    exc = RuntimeError("boom")
    exc.body = {"type": "bad_request"}
    summary = provider_clients.anthropic_api_error_summary(exc, max_len=200)

    assert "RuntimeError" in summary
    assert "api_error_type=bad_request" in summary


def test_openai_api_error_summary_covers_nested_body_and_truncation() -> None:
    exc = RuntimeError("boom")
    exc.status_code = 429
    exc.request_id = "  req-1234567890abcdef  "
    exc.body = {
        "error": {
            "type": " rate_limit_error ",
            "message": " too many\nrequests " * 20,
            "code": " rate_limit_exceeded ",
        }
    }

    summary = provider_clients.openai_api_error_summary(exc, max_len=180)

    assert summary.startswith("RuntimeError|http=429|request_id=req-1234567890abcdef")
    assert "api_error_code=rate_limit_exceeded" in summary
    assert "api_error_type=rate_limit_error" in summary
    assert "api_error_message=too many requests" in summary
    assert "\n" not in summary
    assert len(summary) == 180


def test_openai_api_error_summary_handles_missing_and_non_dict_body() -> None:
    exc = RuntimeError("boom")
    exc.status_code = 500
    exc.body = ["not", "a", "dict"]

    summary = provider_clients.openai_api_error_summary(exc)

    assert summary == "RuntimeError|http=500"


def test_openai_api_error_summary_uses_top_level_body_fallback_fields() -> None:
    exc = RuntimeError("boom")
    exc.body = {
        "type": " invalid_request_error ",
        "message": " bad\nrequest ",
    }

    summary = provider_clients.openai_api_error_summary(exc)

    assert "api_error_type=invalid_request_error" in summary
    assert "api_error_message=bad request" in summary
