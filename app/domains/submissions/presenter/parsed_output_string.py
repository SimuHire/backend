from __future__ import annotations

from app.domains.submissions.presenter.parsed_output_utils import sanitize_stream


def process_string_output(
    parsed_output: str, *, include_output: bool, max_output_chars: int
):
    text, truncated = sanitize_stream(parsed_output, max_chars=max_output_chars)
    return (
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        truncated,
        truncated,
        text if include_output else None,
        None,
    )
