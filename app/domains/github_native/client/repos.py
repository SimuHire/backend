from __future__ import annotations

from .names import split_full_name
from .transport import GithubTransport


class RepoOperations:
    transport: GithubTransport
    default_org: str | None

    async def generate_repo_from_template(
        self,
        *,
        template_full_name: str,
        new_repo_name: str,
        owner: str | None = None,
        private: bool = True,
    ) -> dict:
        template_owner, template_repo = split_full_name(template_full_name)
        payload = {
            "owner": owner or self.default_org,
            "name": new_repo_name,
            "include_all_branches": False,
            "private": private,
        }
        path = f"/repos/{template_owner}/{template_repo}/generate"
        return await self._request("POST", path, json=payload)

    async def add_collaborator(
        self, repo_full_name: str, username: str, *, permission: str = "push"
    ) -> dict:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/collaborators/{username}"
        return await self._request("PUT", path, json={"permission": permission})
