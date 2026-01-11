from __future__ import annotations

import argparse
import asyncio
import sys

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health import check_template_health
from app.domains.tasks.template_catalog import ALLOWED_TEMPLATE_KEYS
from app.infra.config import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tenon template health checker")
    parser.add_argument(
        "--mode",
        choices=["static", "live"],
        default="static",
        help="Check mode",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all template keys in the catalog",
    )
    parser.add_argument(
        "--template-keys",
        nargs="*",
        default=[],
        help="Specific template keys to check",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Concurrent checks to run",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Live check timeout per template",
    )
    return parser.parse_args()


def _validate_config() -> tuple[bool, str]:
    if not (settings.github.GITHUB_TOKEN or "").strip():
        return False, "TENON_GITHUB_TOKEN is required"
    if not (settings.github.GITHUB_ACTIONS_WORKFLOW_FILE or "").strip():
        return False, "TENON_GITHUB_ACTIONS_WORKFLOW_FILE is required"
    return True, ""


async def _run(args: argparse.Namespace) -> int:
    valid, message = _validate_config()
    if not valid:
        print(f"error: {message}")
        return 2

    if args.all:
        template_keys = list(ALLOWED_TEMPLATE_KEYS)
    else:
        template_keys = list(args.template_keys or [])
    if not template_keys:
        print("error: provide --all or --template-keys")
        return 2

    invalid = [key for key in template_keys if key not in ALLOWED_TEMPLATE_KEYS]
    if invalid:
        print(f"error: invalid template keys: {', '.join(invalid)}")
        return 2

    concurrency = max(1, args.concurrency)
    timeout_seconds = max(1, min(args.timeout_seconds, 600))

    client = GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )
    result = await check_template_health(
        client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        mode=args.mode,
        template_keys=template_keys,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
    )

    ok_count = sum(1 for item in result.templates if item.ok)
    total = len(result.templates)
    print(f"template health ({result.mode}): {ok_count}/{total} ok")
    for item in result.templates:
        if item.ok:
            continue
        joined = ", ".join(item.errors) if item.errors else "unknown_error"
        print(f"- {item.templateKey} ({item.repoFullName}): {joined}")

    return 0 if result.ok else 1


def main() -> None:
    """CLI entrypoint."""
    args = _parse_args()
    try:
        exit_code = asyncio.run(_run(args))
    except KeyboardInterrupt:
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
