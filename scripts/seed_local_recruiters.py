import asyncio

from sqlalchemy import select

from app.domains import Base
from app.domains.companies.models import Company
from app.domains.users.models import User
from app.infra.db import async_session_maker, engine


async def main():
    """Seed default recruiters for local development."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as s:
        # Ensure company exists
        c = await s.scalar(select(Company).where(Company.name == "LocalCo"))
        if not c:
            c = Company(name="LocalCo")
            s.add(c)
            await s.flush()

        recruiters = [
            ("Local Recruiter 1", "recruiter1@local.test"),
            ("Local Recruiter 2", "recruiter2@local.test"),
        ]

        created = []
        for name, email in recruiters:
            u = await s.scalar(select(User).where(User.email == email))
            if not u:
                u = User(
                    name=name,
                    email=email,
                    role="recruiter",
                    company_id=c.id,
                    password_hash=None,
                )
                s.add(u)
                created.append(email)

        await s.commit()

        if created:
            print(f"Seeded: {', '.join(created)}")
        else:
            print("Recruiters already exist (no changes).")


if __name__ == "__main__":
    asyncio.run(main())
