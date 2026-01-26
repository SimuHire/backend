from __future__ import annotations

from .names import split_full_name
from .requests import get_bytes, request_json
from .transport import GithubTransport


class CompatOperations:
    transport: GithubTransport

    def _split_full_name(self, full_name: str):
        return split_full_name(full_name)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params=None,
        json=None,
        expect_body: bool = True,
    ):
        return await request_json(
            self.transport,
            method,
            path,
            params=params,
            json=json,
            expect_body=expect_body,
        )

    async def _get_json(self, path: str, params=None):
        return await self._request("GET", path, params=params)

    async def _post_json(self, path: str, *, json: dict, expect_body: bool = True):
        return await self._request("POST", path, json=json, expect_body=expect_body)

    async def _put_json(self, path: str, *, json: dict | None = None):
        return await self._request("PUT", path, json=json)

    async def _get_bytes(self, path: str, params=None) -> bytes:
        return await get_bytes(self.transport, path, params=params)
