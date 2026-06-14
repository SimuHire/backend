"""OpenAI-backed transcription provider."""

from __future__ import annotations

import mimetypes
import os
import tempfile
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from app.ai import resolve_transcription_config
from app.ai.ai_provider_clients_service import (
    api_key_configured,
    openai_api_error_summary,
)
from app.config import settings
from app.integrations.transcription.integrations_transcription_base_client import (
    TranscriptionProvider,
    TranscriptionProviderError,
    TranscriptionResult,
)

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
_LOCAL_FASTER_WHISPER_MODEL_SIZE = "tiny.en"
_LOCAL_FASTER_WHISPER_MODEL_NAME = f"faster-whisper-{_LOCAL_FASTER_WHISPER_MODEL_SIZE}"


def _is_retryable_openai_error(exc: Exception) -> bool:
    parts = [type(exc).__name__, str(exc)]
    normalized = " ".join(part for part in parts if part).strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _RETRYABLE_OPENAI_ERROR_MARKERS)


def _candidate_models(primary_model: str) -> list[str]:
    models: list[str] = []
    for model_name in (primary_model, "whisper-1"):
        normalized = (model_name or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)
    return models


@lru_cache(maxsize=1)
def _get_local_faster_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TranscriptionProviderError(
            "local_transcription_sdk_not_installed"
        ) from exc
    return WhisperModel(
        _LOCAL_FASTER_WHISPER_MODEL_SIZE,
        device="cpu",
        compute_type="int8",
    )


def _normalize_local_whisper_segments(segments: Any) -> list[dict[str, object]]:
    normalized_segments: list[dict[str, object]] = []
    for item in segments:
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        normalized_segments.append(
            {
                "startMs": max(
                    0, int(float(getattr(item, "start", 0.0) or 0.0) * 1000)
                ),
                "endMs": max(0, int(float(getattr(item, "end", 0.0) or 0.0) * 1000)),
                "text": text,
            }
        )
    return normalized_segments


def _transcribe_locally_with_faster_whisper(file_path: str) -> TranscriptionResult:
    try:
        model = _get_local_faster_whisper_model()
        segments, _info = model.transcribe(
            file_path,
            beam_size=1,
            vad_filter=True,
        )
        normalized_segments = _normalize_local_whisper_segments(list(segments))
    except TranscriptionProviderError:
        raise
    except Exception as exc:  # pragma: no cover - depends on environment/runtime
        raise TranscriptionProviderError(
            f"local_transcription_failed:{type(exc).__name__}"
        ) from exc
    transcript_text = " ".join(
        segment["text"] for segment in normalized_segments if segment.get("text")
    ).strip()
    if not transcript_text:
        raise TranscriptionProviderError("local_transcription_failed:empty_transcript")
    return TranscriptionResult(
        text=transcript_text,
        segments=normalized_segments,
        model_name=_LOCAL_FASTER_WHISPER_MODEL_NAME,
    )


def _guess_extension(content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    extension = mimetypes.guess_extension(normalized or "") or ""
    if extension == ".jpe":
        return ".jpg"
    return extension


def _candidate_filenames(*urls: str) -> list[str]:
    candidates: list[str] = []
    for raw_url in urls:
        if not raw_url:
            continue
        parsed = urlparse(raw_url)
        key = ((parse_qs(parsed.query).get("key") or [""])[0] or "").strip()
        if key:
            candidates.append(unquote(key.rsplit("/", 1)[-1]))
        path_name = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
        if path_name:
            candidates.append(path_name)
    return candidates


def _infer_filename(
    *,
    source_url: str,
    final_url: str,
    content_type: str | None,
) -> str:
    for candidate in _candidate_filenames(source_url, final_url):
        root, extension = os.path.splitext(candidate)
        if root:
            if extension:
                return candidate
            guessed = _guess_extension(content_type)
            return f"{candidate}{guessed}" if guessed else candidate
    guessed = _guess_extension(content_type)
    return f"recording{guessed or '.bin'}"


def _read_signed_media(
    *,
    source_url: str,
    content_type: str,
    timeout_seconds: int,
) -> tuple[bytes, str, str]:
    request = Request(source_url, headers={"User-Agent": "Winoe-AI/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
            response_type = response.headers.get("Content-Type")
            final_url = response.geturl()
    except Exception as exc:  # pragma: no cover - network variability
        raise TranscriptionProviderError(
            f"download_failed:{type(exc).__name__}"
        ) from exc
    if not payload:
        raise TranscriptionProviderError("download_failed:empty_body")
    normalized_type = (response_type or content_type or "").split(";", 1)[
        0
    ].strip().lower() or "application/octet-stream"
    return (
        payload,
        _infer_filename(
            source_url=source_url,
            final_url=final_url,
            content_type=normalized_type,
        ),
        normalized_type,
    )


def _dump_object(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    return value


def _segment_text(segment: dict[str, Any]) -> str | None:
    text = segment.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _coerce_millis(value: Any, *, key_name: str) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        numeric = float(value)
        if key_name in {"start", "end"}:
            numeric *= 1000.0
        return max(0, int(numeric))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            numeric = float(stripped)
        except ValueError:
            return 0
        if key_name in {"start", "end"}:
            numeric *= 1000.0
        return max(0, int(numeric))
    return 0


def _normalize_segment(segment: Any) -> dict[str, object] | None:
    normalized = _dump_object(segment)
    if not isinstance(normalized, dict):
        return None
    text = _segment_text(normalized)
    if text is None:
        return None
    start_key = (
        "startMs"
        if "startMs" in normalized
        else "start_ms"
        if "start_ms" in normalized
        else "start"
    )
    end_key = (
        "endMs"
        if "endMs" in normalized
        else "end_ms"
        if "end_ms" in normalized
        else "end"
    )
    return {
        "startMs": _coerce_millis(normalized.get(start_key), key_name=start_key),
        "endMs": _coerce_millis(normalized.get(end_key), key_name=end_key),
        "text": text,
    }


def _normalize_segments(
    raw_segments: Any, *, transcript_text: str
) -> list[dict[str, object]]:
    if isinstance(raw_segments, list):
        normalized_segments = [
            segment
            for item in raw_segments
            if (segment := _normalize_segment(item)) is not None
        ]
        if normalized_segments:
            return normalized_segments
    if transcript_text.strip():
        return [{"startMs": 0, "endMs": 0, "text": transcript_text.strip()}]
    return []


def _extract_text(payload: Any) -> str:
    normalized = _dump_object(payload)
    if isinstance(normalized, dict):
        text = normalized.get("text")
        if isinstance(text, str):
            return text.strip()
    if hasattr(payload, "text") and isinstance(payload.text, str):
        return payload.text.strip()
    if isinstance(payload, str):
        return payload.strip()
    return ""


class OpenAITranscriptionProvider(TranscriptionProvider):
    """Transcribe signed recording URLs with OpenAI audio models."""

    def transcribe_recording(
        self,
        *,
        source_url: str,
        content_type: str,
    ) -> TranscriptionResult:
        """Execute transcribe recording."""
        if not source_url:
            raise TranscriptionProviderError("source_url is required")
        config = resolve_transcription_config()
        if not api_key_configured(settings.OPENAI_API_KEY):
            raise TranscriptionProviderError("missing_openai_api_key")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise TranscriptionProviderError("openai_sdk_not_installed") from exc

        media_bytes, filename, normalized_type = _read_signed_media(
            source_url=source_url,
            content_type=content_type,
            timeout_seconds=config.timeout_seconds,
        )
        suffix = os.path.splitext(filename)[1] or _guess_extension(normalized_type)
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

        with tempfile.NamedTemporaryFile(suffix=suffix or ".bin") as handle:
            handle.write(media_bytes)
            handle.flush()
            try:
                with open(handle.name, "rb") as audio_file:
                    response = None
                    response_model = None
                    openai_error = None
                    candidate_models = _candidate_models(config.model)
                    for index, model_name in enumerate(candidate_models):
                        audio_file.seek(0)
                        try:
                            response = client.audio.transcriptions.create(
                                file=audio_file,
                                model=model_name,
                                response_format="json",
                            )
                            response_model = model_name
                            break
                        except Exception as exc:
                            openai_error = exc
                            if not _is_retryable_openai_error(exc):
                                raise
                            if index >= len(candidate_models) - 1:
                                break
                    if response is None:
                        if openai_error is None:
                            raise RuntimeError("openai_transcription_failed:unknown")
                        if _is_retryable_openai_error(openai_error):
                            return _transcribe_locally_with_faster_whisper(handle.name)
                        raise openai_error
            except Exception as exc:  # pragma: no cover - network/provider variability
                raise TranscriptionProviderError(
                    f"openai_transcription_failed:{openai_api_error_summary(exc)}"
                ) from exc

        transcript_text = _extract_text(response)
        payload = _dump_object(response)
        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        return TranscriptionResult(
            text=transcript_text,
            segments=_normalize_segments(raw_segments, transcript_text=transcript_text),
            model_name=response_model or config.model,
        )


__all__ = ["OpenAITranscriptionProvider"]
