from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infra.config import settings
from app.infra.proxy_headers import TrustedProxyHeadersMiddleware, trusted_proxy_cidrs
from app.infra.request_limits import RequestSizeLimitMiddleware


def configure_proxy_headers(app: FastAPI) -> None:
    cidrs = trusted_proxy_cidrs()
    if cidrs:
        app.add_middleware(TrustedProxyHeadersMiddleware, trusted_proxy_cidrs=cidrs)


def configure_request_limits(app: FastAPI) -> None:
    app.add_middleware(
        RequestSizeLimitMiddleware, max_body_bytes=settings.MAX_REQUEST_BODY_BYTES
    )


def configure_cors(app: FastAPI) -> None:
    cors_cfg = getattr(settings, "cors", None)
    origins = list(cors_cfg.CORS_ALLOW_ORIGINS or []) if cors_cfg else []
    origin_regex = cors_cfg.CORS_ALLOW_ORIGIN_REGEX if cors_cfg else None
    if not origins and not origin_regex:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


__all__ = [
    "configure_proxy_headers",
    "configure_request_limits",
    "configure_cors",
]
