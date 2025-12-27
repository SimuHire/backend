from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CandidateSession, Company, Simulation, Submission, Task, User
from app.domain.simulations.blueprints import DEFAULT_5_DAY_BLUEPRINT


async def create_company(session: AsyncSession, *, name: str = "Acme Corp") -> Company:
    company = Company(name=name)
    session.add(company)
    await session.flush()
    return company


async def create_recruiter(
    session: AsyncSession,
    *,
    email: str = "recruiter@example.com",
    company: Company | None = None,
    company_name: str | None = None,
    name: str | None = None,
) -> User:
    company = company or await create_company(
        session, name=company_name or f"{email}-co"
    )
    user = User(
        name=name or email.split("@")[0],
        email=email,
        role="recruiter",
        company_id=company.id,
        password_hash="",
    )
    session.add(user)
    await session.flush()
    return user


async def create_simulation(
    session: AsyncSession,
    *,
    created_by: User,
    title: str = "Backend Simulation",
    role: str = "Backend Engineer",
    tech_stack: str = "Node.js, PostgreSQL",
    seniority: str = "Mid",
    focus: str = "Deliver a backend feature over 5 days",
) -> tuple[Simulation, list[Task]]:
    sim = Simulation(
        company_id=created_by.company_id,
        title=title,
        role=role,
        tech_stack=tech_stack,
        seniority=seniority,
        focus=focus,
        scenario_template="default-5day-node-postgres",
        created_by=created_by.id,
        status="active",
    )
    session.add(sim)
    await session.flush()

    tasks: list[Task] = []
    for blueprint_task in DEFAULT_5_DAY_BLUEPRINT:
        template_repo = None
        if blueprint_task["type"] in {"code", "debug"}:
            template_repo = "simuhire-templates/demo-template"
        task = Task(
            simulation_id=sim.id,
            day_index=blueprint_task["day_index"],
            type=blueprint_task["type"],
            title=blueprint_task["title"],
            description=blueprint_task["description"],
            template_repo=template_repo,
        )
        session.add(task)
        tasks.append(task)

    await session.flush()
    tasks.sort(key=lambda t: t.day_index)
    return sim, tasks


async def create_candidate_session(
    session: AsyncSession,
    *,
    simulation: Simulation,
    candidate_name: str = "Jane Candidate",
    invite_email: str = "jane@example.com",
    status: str = "not_started",
    token: str | None = None,
    expires_in_days: int = 14,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> CandidateSession:
    token = token or secrets.token_urlsafe(16)
    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    cs = CandidateSession(
        simulation_id=simulation.id,
        candidate_user_id=None,
        candidate_name=candidate_name,
        invite_email=invite_email,
        token=token,
        status=status,
        expires_at=expires_at,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(cs)
    await session.flush()
    return cs


async def create_submission(
    session: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task: Task,
    content_text: str | None = None,
    code_blob: str | None = None,
    submitted_at: datetime | None = None,
    tests_passed: int | None = None,
    tests_failed: int | None = None,
    test_output: str | None = None,
    code_repo_path: str | None = None,
    last_run_at: datetime | None = None,
    commit_sha: str | None = None,
    workflow_run_id: str | None = None,
    diff_summary_json: str | None = None,
) -> Submission:
    submission = Submission(
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        submitted_at=submitted_at or datetime.now(UTC),
        content_text=content_text,
        code_blob=code_blob,
        code_repo_path=code_repo_path,
        commit_sha=commit_sha,
        workflow_run_id=workflow_run_id,
        diff_summary_json=diff_summary_json,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        test_output=test_output,
        last_run_at=last_run_at,
    )
    session.add(submission)
    await session.flush()
    return submission
