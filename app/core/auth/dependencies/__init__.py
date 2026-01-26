from __future__ import annotations

import sys

from app.core.auth.principal import get_principal
from app.core.settings import settings

from .current_user import get_current_user
from .db import lookup_user as _lookup_user
from .dev_bypass import dev_bypass_user
from .env import _env_name_base, env_name
from .env import env_name as _env_name
from .users import user_from_principal

_dev_bypass_user = dev_bypass_user
_user_from_principal = user_from_principal

__all__ = [
    "_env_name",
    "_dev_bypass_user",
    "_env_name_base",
    "_lookup_user",
    "_user_from_principal",
    "get_principal",
    "dev_bypass_user",
    "env_name",
    "get_current_user",
    "settings",
    "sys",
    "user_from_principal",
]
