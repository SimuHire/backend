from __future__ import annotations

from typing import Any


def summarize_diff(
    compare_payload: dict[str, Any], *, base: str | None, head: str | None
) -> dict[str, Any]:
    """Reduce GitHub compare payload into a compact summary."""
    files = []
    for f in compare_payload.get("files") or []:
        files.append(
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "changes": f.get("changes"),
                "patch": f.get("patch"),
            }
        )
    return {
        "ahead_by": compare_payload.get("ahead_by"),
        "behind_by": compare_payload.get("behind_by"),
        "total_commits": compare_payload.get("total_commits"),
        "base": base,
        "head": head,
        "files": files,
    }
