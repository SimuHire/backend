from __future__ import annotations

# Backwards-compatible re-exports to satisfy existing imports/tests.
from app.core.config import settings  # noqa: F401
from app.core.db import async_session_maker  # noqa: F401
from app.core.security import auth0  # noqa: F401
from app.core.security.dependencies import _env_name, get_current_user  # noqa: F401
