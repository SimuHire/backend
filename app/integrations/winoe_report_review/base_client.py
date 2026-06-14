"""Winoe Report review provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ai import AggregatedWinoeReportOutput, DayReviewerOutput


class WinoeReportReviewProviderError(RuntimeError):
    """Raised when winoe-report review provider execution fails."""


@dataclass(frozen=True, slots=True)
class WinoeReportDayReviewRequest:
    """Structured request for a single reviewer agent."""

    agent_key: str
    fallback_provider: str
    system_prompt: str
    user_prompt: str
    model: str


@dataclass(frozen=True, slots=True)
class WinoeReportAggregateRequest:
    """Structured request for the winoe-report aggregator."""

    agent_key: str
    fallback_provider: str
    system_prompt: str
    user_prompt: str
    model: str


class WinoeReportReviewProvider(Protocol):
    """Provider contract for winoe-report review workloads."""

    def review_day(
        self,
        *,
        request: WinoeReportDayReviewRequest,
    ) -> DayReviewerOutput:
        """Review one day artifact."""
        ...

    def aggregate_winoe_report(
        self,
        *,
        request: WinoeReportAggregateRequest,
    ) -> AggregatedWinoeReportOutput:
        """Aggregate reviewer outputs into one winoe report."""
        ...


__all__ = [
    "WinoeReportAggregateRequest",
    "WinoeReportDayReviewRequest",
    "WinoeReportReviewProvider",
    "WinoeReportReviewProviderError",
]
