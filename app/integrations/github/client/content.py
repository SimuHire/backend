from __future__ import annotations

from .names import split_full_name
from .transport import GithubTransport


class ContentOperations:
    transport: GithubTransport

    async def get_branch(self, repo_full_name: str, branch: str) -> dict:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/branches/{branch}"
        return await self._get_json(path)

    async def get_repo(self, repo_full_name: str) -> dict:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}"
        return await self._get_json(path)

    async def get_file_contents(
        self, repo_full_name: str, file_path: str, *, ref: str | None = None
    ) -> dict:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/contents/{file_path}"
        params = {"ref": ref} if ref else None
        return await self._get_json(path, params=params)

    async def get_compare(self, repo_full_name: str, base: str, head: str) -> dict:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/compare/{base}...{head}"
        return await self._get_json(path)
