from __future__ import annotations

from app.domains.submissions.presenter.parsed_output_dict import process_dict_output
from app.domains.submissions.presenter.parsed_output_string import (
    process_string_output,
)
from app.domains.submissions.presenter.parsed_output_utils import _safe_int


def process_parsed_output(
    parsed_output, *, include_output: bool, max_output_chars: int
):
    if isinstance(parsed_output, dict):
        if not parsed_output:
            return (None,) * 13
        return process_dict_output(
            parsed_output,
            include_output=include_output,
            max_output_chars=max_output_chars,
        )
    if isinstance(parsed_output, str):
        return process_string_output(
            parsed_output,
            include_output=include_output,
            max_output_chars=max_output_chars,
        )
    return (None,) * 13


__all__ = ["process_parsed_output", "_safe_int"]
