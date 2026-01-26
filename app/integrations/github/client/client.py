from __future__ import annotations

from .artifacts import ArtifactOperations
from .compat import CompatOperations
from .content import ContentOperations
from .repos import RepoOperations
from .transport import GithubTransport
from .workflows import WorkflowOperations


class GithubClient(
    RepoOperations,
    WorkflowOperations,
    ContentOperations,
    ArtifactOperations,
    CompatOperations,
):
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        default_org: str | None = None,
        transport=None,
    ):
        self.transport = GithubTransport(
            base_url=base_url,
            token=token,
            transport=transport,
        )
        self.default_org = default_org

    async def aclose(self) -> None:
        await self.transport.aclose()
