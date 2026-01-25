from __future__ import annotations

from app.domains.submissions.presenter.parsed_output_utils import _safe_int


def fill_counts(sub, passed_val, failed_val, total_val):
    if passed_val is None:
        passed_val = _safe_int(getattr(sub, "tests_passed", None))
    if failed_val is None:
        failed_val = _safe_int(getattr(sub, "tests_failed", None))
    if total_val is None:
        total_val = _safe_int(getattr(sub, "tests_total", None))
    if total_val is None and (passed_val is not None or failed_val is not None):
        total_val = (passed_val or 0) + (failed_val or 0)
    return passed_val, failed_val, total_val
