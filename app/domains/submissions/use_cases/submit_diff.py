from __future__ import annotations

import json

from app.domains.github_native.client import GithubClient
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.services.workspace_records import Workspace


async def build_diff_summary(
    github_client: GithubClient, workspace: Workspace, branch: str, head_sha: str
) -> str | None:
    base_sha = workspace.base_template_sha or branch
    compare = await github_client.get_compare(
        workspace.repo_full_name, base_sha, head_sha
    )
    return json.dumps(
        submission_service.summarize_diff(compare, base=base_sha, head=head_sha),
        ensure_ascii=False,
    )
