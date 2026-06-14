"""Scenario-generation provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ai import ScenarioGenerationOutput


class ScenarioGenerationProviderError(RuntimeError):
    """Raised when scenario-generation provider execution fails."""


@dataclass(frozen=True, slots=True)
class ScenarioGenerationProviderRequest:
    """Structured prompt request for scenario-generation providers."""

    agent_key: str
    fallback_provider: str
    system_prompt: str
    user_prompt: str
    model: str


@dataclass(frozen=True, slots=True)
class ScenarioGenerationProviderResponse:
    """Structured provider response for scenario generation."""

    result: ScenarioGenerationOutput
    model_name: str
    model_version: str


class ScenarioGenerationProvider(Protocol):
    """Provider contract for generating scenario payloads."""

    def generate_scenario(
        self,
        *,
        request: ScenarioGenerationProviderRequest,
    ) -> ScenarioGenerationProviderResponse:
        """Generate a scenario."""
        ...


__all__ = [
    "ScenarioGenerationProvider",
    "ScenarioGenerationProviderError",
    "ScenarioGenerationProviderRequest",
    "ScenarioGenerationProviderResponse",
]
