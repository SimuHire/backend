from __future__ import annotations


def build_workflow_fallbacks(workflow_file: str) -> list[str]:
    return list(
        dict.fromkeys(
            [workflow_file, "tenon-ci.yml", ".github/workflows/tenon-ci.yml"]
        )
    )
