from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.ai_model_preflight_service import (
    build_ai_model_matrix_rows,
    build_ai_model_preflight_targets,
    verify_ai_model_preflight,
)
from app.ai.ai_provider_clients_service import AIProviderExecutionError


def test_model_matrix_includes_primary_and_fallback_bindings() -> None:
    rows = build_ai_model_matrix_rows()

    assert len(rows) == 13
    expected_bindings = {
        (
            "Prestart / Project Brief Creator",
            "primary",
            "structured_json",
            "anthropic",
            "claude-opus-4-7",
        ),
        (
            "Prestart / Project Brief Creator",
            "fallback",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Design Doc Reviewer",
            "primary",
            "structured_json",
            "anthropic",
            "claude-opus-4-7",
        ),
        (
            "Design Doc Reviewer",
            "fallback",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Code Implementation Reviewer",
            "primary",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Code Implementation Reviewer",
            "fallback",
            "structured_json",
            "anthropic",
            "claude-sonnet-4-6",
        ),
        (
            "Demo Presentation Reviewer",
            "primary",
            "structured_json",
            "anthropic",
            "claude-sonnet-4-6",
        ),
        (
            "Demo Presentation Reviewer",
            "fallback",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Reflection Essay Reviewer",
            "primary",
            "structured_json",
            "anthropic",
            "claude-sonnet-4-6",
        ),
        (
            "Reflection Essay Reviewer",
            "fallback",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Winoe, the Talent Intelligence Agent",
            "primary",
            "structured_json",
            "openai",
            "gpt-5.5",
        ),
        (
            "Winoe, the Talent Intelligence Agent",
            "fallback",
            "structured_json",
            "anthropic",
            "claude-sonnet-4-6",
        ),
        ("Transcription", "primary", "transcription", "openai", "gpt-4o-transcribe"),
    }
    assert {
        (row.feature, row.role, row.capability, row.provider, row.model) for row in rows
    } == expected_bindings
    assert all(
        row.prompt_version.startswith("winoe-ai-pack-v4:")
        or row.prompt_version == "n/a"
        for row in rows
    )
    assert {row.capability for row in rows} == {"structured_json", "transcription"}

    targets = build_ai_model_preflight_targets()
    assert {
        (target.capability, target.provider, target.model) for target in targets
    } == {
        ("structured_json", "anthropic", "claude-opus-4-7"),
        ("structured_json", "anthropic", "claude-sonnet-4-6"),
        ("structured_json", "openai", "gpt-5.5"),
        ("transcription", "openai", "gpt-4o-transcribe"),
    }


def test_verify_ai_model_preflight_raises_on_unreachable_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_verify(*, provider: str, model: str) -> None:
        calls.append((provider, model))
        if (provider, model) == ("anthropic", "claude-sonnet-4-6"):
            raise AIProviderExecutionError("anthropic_request_failed:TimeoutError")

    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.verify_ai_model_endpoint",
        _fake_verify,
    )

    with pytest.raises(RuntimeError, match="model_preflight_failed"):
        verify_ai_model_preflight()

    assert ("anthropic", "claude-sonnet-4-6") in calls


def test_verify_ai_model_preflight_uses_structured_output_probes(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _fake_openai(
        *, api_key, model, system_prompt, user_prompt, response_model, **_kwargs
    ):
        calls.append(("openai", model, response_model.__name__))
        return response_model(ok=True)

    def _fake_anthropic(
        *, api_key, model, system_prompt, user_prompt, response_model, **_kwargs
    ):
        calls.append(("anthropic", model, response_model.__name__))
        return response_model(ok=True)

    def _fake_transcription(*, model: str) -> None:
        calls.append(("openai-transcription", model, "probe"))

    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_openai_json_schema",
        _fake_openai,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_anthropic_json",
        _fake_anthropic,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service._openai_transcription_model_reachable",
        _fake_transcription,
    )

    results = verify_ai_model_preflight()

    assert all(result.reachable for result in results)
    assert {result.capability for result in results} == {
        "structured_json",
        "transcription",
    }
    assert ("openai", "gpt-5.5", "_ModelPreflightProbeOutput") in calls
    assert ("anthropic", "claude-opus-4-7", "_ModelPreflightProbeOutput") in calls
    assert ("openai-transcription", "gpt-4o-transcribe", "probe") in calls


def test_verify_ai_model_preflight_fails_when_structured_probe_fails(
    monkeypatch,
) -> None:
    def _fake_openai(**_kwargs):
        raise AIProviderExecutionError("openai_request_failed:BadRequestError")

    def _fake_anthropic(**_kwargs):
        return type("Probe", (), {"ok": True})

    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_openai_json_schema",
        _fake_openai,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_anthropic_json",
        _fake_anthropic,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service._openai_transcription_model_reachable",
        lambda **_kwargs: None,
    )

    with pytest.raises(RuntimeError, match="model_preflight_failed"):
        verify_ai_model_preflight()


def test_verify_ai_model_preflight_fails_when_transcription_probe_fails(
    monkeypatch,
) -> None:
    def _fake_openai(**_kwargs):
        return type("Probe", (), {"ok": True})

    def _fake_anthropic(**_kwargs):
        return type("Probe", (), {"ok": True})

    def _fake_transcription(*, model: str) -> None:
        raise AIProviderExecutionError(
            "openai_transcription_failed:BadRequestError|http=400|api_error_message=Bad audio"
        )

    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_openai_json_schema",
        _fake_openai,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.call_anthropic_json",
        _fake_anthropic,
    )
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service._openai_transcription_model_reachable",
        _fake_transcription,
    )

    with pytest.raises(RuntimeError, match="model_preflight_failed"):
        verify_ai_model_preflight()


def test_verify_ai_model_preflight_rejects_blank_fallback_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.settings.WINOE_REPORT_DAY4_FALLBACK_MODEL",
        "   ",
    )

    with pytest.raises(AIProviderExecutionError, match="missing_model_config"):
        build_ai_model_matrix_rows()


def test_verify_ai_model_preflight_rejects_blank_primary_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.settings.WINOE_REPORT_DAY1_MODEL",
        "",
    )

    with pytest.raises(AIProviderExecutionError, match="missing_model_config"):
        build_ai_model_matrix_rows()


def test_verify_ai_model_preflight_rejects_unsupported_fallback_provider_config(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.ai.ai_model_preflight_service.settings.WINOE_REPORT_DAY4_FALLBACK_PROVIDER",
        "anthropic",
    )

    with pytest.raises(AIProviderExecutionError, match="unsupported_fallback_provider"):
        build_ai_model_matrix_rows()


def test_ai_model_preflight_helpers_cover_route_and_error_branches(monkeypatch) -> None:
    from app.ai import ai_model_preflight_service as preflight

    assert preflight._settings_path("1", "2", "3") == (
        "app/config/config_settings_fields_config.py:1,2,3"
    )

    wav_bytes = preflight._build_silent_wav_bytes(duration_seconds=0.01)
    import io
    import wave

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnframes() > 0

    monkeypatch.setattr(preflight.settings, "OPENAI_API_KEY", None)
    with pytest.raises(AIProviderExecutionError, match="missing_openai_api_key"):
        preflight._openai_model_reachable(model="gpt-5.5")
    with pytest.raises(AIProviderExecutionError, match="missing_openai_api_key"):
        preflight._openai_transcription_model_reachable(model="gpt-4o-transcribe")

    monkeypatch.setattr(preflight.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(preflight.settings, "ANTHROPIC_API_KEY", None)
    with pytest.raises(AIProviderExecutionError, match="missing_anthropic_api_key"):
        preflight._anthropic_model_reachable(model="claude-opus-4-7")

    import sys

    class _FakeAudioTranscriptions:
        def __init__(self, *, should_raise: bool = False):
            self.should_raise = should_raise
            self.captured: dict[str, object] = {}

        def create(self, **kwargs):
            self.captured.update(kwargs)
            self.captured["file_header"] = kwargs["file"].read(4)
            if self.should_raise:
                exc = RuntimeError("bad request")
                exc.status_code = 429
                exc.request_id = " req-abc "
                exc.body = {
                    "error": {
                        "type": " rate_limit_error ",
                        "message": " too many\nrequests ",
                        "code": " rate_limit_exceeded ",
                    }
                }
                raise exc
            return SimpleNamespace()

    success_transcriptions = _FakeAudioTranscriptions()

    class _FakeOpenAISuccess:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=success_transcriptions)

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAISuccess)
    )
    preflight._openai_transcription_model_reachable(model="gpt-4o-transcribe")
    assert success_transcriptions.captured["model"] == "gpt-4o-transcribe"
    assert success_transcriptions.captured["response_format"] == "json"
    assert success_transcriptions.captured["file_header"] == b"RIFF"

    failing_transcriptions = _FakeAudioTranscriptions(should_raise=True)

    class _FakeOpenAIFailure:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=failing_transcriptions)

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAIFailure)
    )
    with pytest.raises(
        AIProviderExecutionError,
        match=(
            r"openai_transcription_failed:RuntimeError\|http=429\|request_id=req-abc"
            r"\|api_error_code=rate_limit_exceeded\|api_error_type=rate_limit_error"
        ),
    ):
        preflight._openai_transcription_model_reachable(model="gpt-4o-transcribe")

    structured_calls: list[tuple[str, str]] = []
    transcription_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        preflight,
        "_openai_model_reachable",
        lambda *, model: structured_calls.append(("structured", model)),
    )
    monkeypatch.setattr(
        preflight,
        "_openai_transcription_model_reachable",
        lambda *, model: transcription_calls.append(("transcription", model, "called")),
    )
    monkeypatch.setattr(
        preflight,
        "build_ai_model_matrix_rows",
        lambda: [
            SimpleNamespace(
                provider="openai", model="gpt-5.5", capability="structured_json"
            ),
            SimpleNamespace(
                provider="openai", model="gpt-4o-transcribe", capability="transcription"
            ),
        ],
    )

    preflight.verify_ai_model_endpoint(provider="openai", model="gpt-5.5")
    preflight.verify_ai_model_endpoint(provider="openai", model="gpt-4o-transcribe")

    assert structured_calls == [("structured", "gpt-5.5")]
    assert transcription_calls == [("transcription", "gpt-4o-transcribe", "called")]

    monkeypatch.setattr(preflight, "build_ai_model_matrix_rows", lambda: [])
    with pytest.raises(AIProviderExecutionError, match="unknown_model_target"):
        preflight.verify_ai_model_endpoint(provider="openai", model="missing")

    monkeypatch.setattr(
        preflight,
        "build_ai_model_matrix_rows",
        lambda: [
            SimpleNamespace(provider="openai", model="gpt-5.5", capability="audio"),
        ],
    )
    with pytest.raises(AIProviderExecutionError, match="unsupported_probe_capability"):
        preflight.verify_ai_model_endpoint(provider="openai", model="gpt-5.5")

    with pytest.raises(AIProviderExecutionError, match="unsupported_provider"):
        preflight.verify_ai_model_endpoint(provider="gemini", model="flash")
