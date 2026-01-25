from __future__ import annotations

import ipaddress

from app.infra.config import settings


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_valid_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value)
        return True
    except ValueError:
        return False


def _ip_in_trusted(host: str, networks: list[ipaddress._BaseNetwork]) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def trusted_proxy_cidrs() -> list[str]:
    return list(settings.TRUSTED_PROXY_CIDRS or [])


class TrustedProxyHeadersMiddleware:
    def __init__(self, app, trusted_proxy_cidrs: list[str] | None = None) -> None:
        cidrs = trusted_proxy_cidrs if trusted_proxy_cidrs is not None else []
        self.app = app
        self._trusted_networks = [
            ipaddress.ip_network(cidr) for cidr in cidrs if _is_valid_cidr(cidr)
        ]

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self._trusted_networks:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        if not client:
            await self.app(scope, receive, send)
            return
        client_host, client_port = client
        if not _ip_in_trusted(client_host, self._trusted_networks):
            await self.app(scope, receive, send)
            return
        forwarded_for = (
            dict(scope.get("headers") or {})
            .get(b"x-forwarded-for", b"")
            .decode("latin1")
            .strip()
        )
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            if _is_valid_ip(first):
                scope["client"] = (first, client_port)
        await self.app(scope, receive, send)


__all__ = ["TrustedProxyHeadersMiddleware", "trusted_proxy_cidrs"]
