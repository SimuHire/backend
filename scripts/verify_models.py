#!/usr/bin/env python3
"""Verify the live reachability of the pinned Winoe AI model matrix."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from app.ai.ai_model_preflight_service import verify_ai_model_preflight


def main() -> int:
    try:
        results = verify_ai_model_preflight()
    except Exception as exc:  # pragma: no cover - script surface
        print(str(exc), file=sys.stderr)
        return 1

    print(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - script surface
    raise SystemExit(main())
