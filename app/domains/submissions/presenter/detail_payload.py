from __future__ import annotations


def build_task_payload(task):
    return {
        "taskId": task.id,
        "dayIndex": task.day_index,
        "type": task.type,
        "title": getattr(task, "title", None),
        "prompt": getattr(task, "prompt", None),
    }


def build_code_payload(sub):
    if sub.code_repo_path is None:
        return None
    return {
        "repoPath": sub.code_repo_path,
        "repoFullName": sub.code_repo_path,
        "repoUrl": f"https://github.com/{sub.code_repo_path}"
        if sub.code_repo_path
        else None,
    }


__all__ = ["build_task_payload", "build_code_payload"]
