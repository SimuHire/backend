from __future__ import annotations

from app.integrations.github.actions_runner.legacy_cache import LegacyCacheMixin
from app.integrations.github.actions_runner.legacy_results import LegacyResultMixin


class RunnerCompatibilityMixin(LegacyResultMixin, LegacyCacheMixin):
    """Compatibility helpers preserved for tests and call sites."""
