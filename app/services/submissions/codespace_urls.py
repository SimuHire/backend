from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.services.submissions.workspace_records import build_codespace_url


def canonical_codespace_url(repo_full_name: str) -> str:
    """Return the normalized Codespaces quickstart URL for a repo."""
    return build_codespace_url(repo_full_name)


def is_canonical_codespace_url(url: str | None) -> bool:
    """Check whether a URL matches the canonical quickstart format."""
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "codespaces.new":
        return False
    query = parse_qs(parsed.query)
    return query.get("quickstart") == ["1"]


async def ensure_canonical_workspace_url(db, workspace) -> str:
    """Persist and return the canonical codespace URL for a workspace."""
    canonical = canonical_codespace_url(workspace.repo_full_name)
    url = workspace.codespace_url
    if is_canonical_codespace_url(url):
        return url
    if url != canonical:
        workspace.codespace_url = canonical
        await db.commit()
        await db.refresh(workspace)
    return canonical
