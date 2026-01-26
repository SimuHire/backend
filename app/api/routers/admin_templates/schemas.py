from __future__ import annotations

from typing import Literal

from app.domains.common.base import APIModel


class TemplateHealthRunRequest(APIModel):
    """Request payload for live template health checks."""

    templateKeys: list[str]
    mode: Literal["live", "static"] = "live"
    timeoutSeconds: int = 180
    concurrency: int = 2
