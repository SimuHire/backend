from __future__ import annotations

import atexit
import logging
import threading
import time
from typing import Any

import httpx
from fastapi import status

from app.infra.config import settings

from .decoder import decode_auth0_token
from .errors import Auth0Error

logger = logging.getLogger(__name__)
_http_client = httpx.Client(timeout=5)
_jwks_cache: dict[str, Any] = {"fetched_at": 0.0, "jwks": None}
_jwks_lock = threading.Lock()


def _close_http_client() -> None:
    _http_client.close()


atexit.register(_close_http_client)


def _fetch_jwks() -> dict[str, Any]:
    response = _http_client.get(settings.auth.jwks_url)
    response.raise_for_status()
    return response.json()


def get_jwks() -> dict[str, Any]:
    now = time.time()
    cached = _jwks_cache.get("jwks")
    ttl = settings.auth.AUTH0_JWKS_CACHE_TTL_SECONDS
    fetched_at = float(_jwks_cache.get("fetched_at") or 0.0)
    if cached is not None and now - fetched_at <= ttl:
        return cached
    try:
        with _jwks_lock:
            now = time.time()
            cached = _jwks_cache.get("jwks")
            fetched_at = float(_jwks_cache.get("fetched_at") or 0.0)
            if cached is not None and now - fetched_at <= ttl:
                return cached
            jwks = _fetch_jwks()
            _jwks_cache["jwks"] = jwks
            _jwks_cache["fetched_at"] = now
            return jwks
    except httpx.HTTPError as exc:
        logger.warning(
            "auth0_jwks_fetch_failed",
            extra={"jwks_url": settings.auth.jwks_url, "reason": "jwks_fetch_failed"},
        )
        raise Auth0Error(
            "Auth provider unavailable", status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from exc


def clear_jwks_cache() -> None:
    with _jwks_lock:
        _jwks_cache["jwks"] = None
        _jwks_cache["fetched_at"] = 0.0


__all__ = [
    "decode_auth0_token",
    "get_jwks",
    "clear_jwks_cache",
    "_fetch_jwks",
    "_jwks_cache",
    "_jwks_lock",
    "_http_client",
    "httpx",
    "settings",
    "Auth0Error",
]
