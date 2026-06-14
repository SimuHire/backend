#!/usr/bin/env python3
"""Seed deterministic Task 3 QA trials for local Talent Partner dashboard testing."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.config import settings
from app.demo.services.task3_local_qa_seed_service import seed_task3_local_qa
from app.shared.database import async_session_maker


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--talent-partner-email",
        default=os.getenv(
            "QA_E2E_TALENT_PARTNER_EMAIL", "winoetalentpartner@gmail.com"
        ),
        help="Must match /api/dev/qa-login default Talent Partner email.",
    )
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    if settings.is_production_environment():
        print("Refusing Task 3 QA seed in production.", file=sys.stderr)
        raise SystemExit(2)
    async with async_session_maker() as db:
        await seed_task3_local_qa(db, talent_partner_email=args.talent_partner_email)
    print(
        "Task 3 QA seed OK for",
        args.talent_partner_email,
        "(run backend with DEV_AUTH_BYPASS=1 and WINOE_ENV=local).",
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
