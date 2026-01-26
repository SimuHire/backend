from __future__ import annotations

import sys


def current_user_module():
    """Return the loaded current_user module."""
    return sys.modules.get("app.core.auth.current_user")
