# SimuHire Backend

FastAPI + Postgres backend for SimuHire, a simulation-based hiring platform. Recruiters create 5-day simulations, invite candidates, and review their task submissions. Candidates progress through tasks via signed tokens (no password flow).

## Architecture

- **Framework**: FastAPI (async) with SQLAlchemy 2.0 and Alembic.
- **Auth**: Auth0 JWTs (bearer) with local/test bypass via `DEV_AUTH_BYPASS` + `x-dev-user-email`.
- **DB**: Postgres (asyncpg); falls back to SQLite `local.db` if no DB URL is set.
- **Domains**:
  - Simulations: recruiter-owned configs seeded with a default 5-day blueprint.
  - Tasks: per-day tasks (design/code/debug/handoff/documentation).
  - Candidate Sessions: invite tokens, expiry, progress state.
  - Submissions: per-task artifacts (text/code) with optional stored test results.
  - Execution Profiles: report placeholder linked 1:1 to a candidate session (creation not implemented).
- **API layout**: `app/api/routes/*` grouped by recruiter vs candidate; services live in `app/domain/**/service*.py`.

## Domain Concepts

- **Simulation**: A 5-day scenario with ordered tasks and metadata (role, techStack, focus).
- **Task**: A single day’s assignment; type drives submission validation.
- **Candidate Session**: Invitation for a candidate; secured by token; tracks started/completed timestamps and expiry.
- **Submission**: Candidate’s response for a task; enforces one-per-task per session; stores text/code and test result fields.
- **Execution Profile**: Future report of performance; model exists but no generation pipeline yet.

## API Overview

- **Health**: `GET /health`
- **Auth**: `GET /api/auth/me`
- **Recruiter – Simulations**
  - `GET /api/simulations` list owned simulations (+candidate counts)
  - `POST /api/simulations` create simulation + default tasks
  - `POST /api/simulations/{simulation_id}/invite` create candidate invite (token/link)
  - `GET /api/simulations/{simulation_id}/candidates` list sessions (`hasReport` if an execution_profile exists)
- **Candidate**
  - `GET /api/candidate/session/{token}` resolve invite; sets `in_progress`
  - `GET /api/candidate/session/{id}/current_task` (header `x-candidate-token`) returns current task, progress; auto-completes if done
  - `POST /api/tasks/{task_id}/submit` (headers `x-candidate-token`, `x-candidate-session-id`) submit current task; validates order and payload
- **Recruiter – Submissions**
  - `GET /api/submissions` (optional `candidateSessionId`, `taskId`) list for owned simulations
  - `GET /api/submissions/{submission_id}` fetch submission detail (content/code/test results)

Auth notes:

- Recruiter routes require Auth0 bearer or local bypass header.
- Candidate routes rely on possession of the invite token; no Auth0.

## Local Development

### Prereqs

- Python 3.11+, Poetry, Postgres (or rely on SQLite fallback).

### Setup

```bash
poetry install
cp .env.example .env   # or configure env vars directly
```

(Repo includes a sample `.env`; replace secrets as needed.)

### Run the app

```bash
# Seed local recruiters (uses SQLite if DB URLs unset)
ENV=local DEV_AUTH_BYPASS=1 poetry run python scripts/seed_local_recruiters.py

# Start API (Hot reload by default)
poetry run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
# or use the helper: ./runBackend.sh
```

### Migrations

```bash
poetry run alembic upgrade head
```

Alembic reads `alembic.ini` and `DATABASE_URL_SYNC`; fallback SQLite uses `local.db` via startup hook.

### Tests

```bash
poetry run pytest          # full suite (coverage thresholds enforced)
poetry run pytest -k api   # focus
```

## Configuration

Key env vars (see `.env`):

- `ENV` (`local`|`test`|`prod`), `API_PREFIX`
- DB: `DATABASE_URL`, `DATABASE_URL_SYNC`
- Auth0: `AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_JWKS_URL`, `AUTH0_API_AUDIENCE`, `AUTH0_ALGORITHMS`
- CORS: `CORS_ALLOW_ORIGINS`, `CORS_ALLOW_ORIGIN_REGEX`
- Candidate portal: `CANDIDATE_PORTAL_BASE_URL` (used to build invite links)
- Dev bypass: `DEV_AUTH_BYPASS=1` enables `x-dev-user-email` on local/test only

## Code Structure

- `app/api` FastAPI routers and application factory
- `app/core` settings, DB session factory, security utilities
- `app/domain` ORM models, schemas, repositories, and services (simulations, candidate_sessions, submissions, users, companies)
- `alembic` migrations; `scripts/` helpers; `tests/` api/unit/integration/property suites

## Typical Flows

- **Run a simulation**: Recruiter authenticates → `POST /api/simulations` seeds 5 tasks → `POST /api/simulations/{id}/invite` sends tokenized link → Candidate resolves token and progresses through tasks via `current_task` and `submit` → Recruiter reviews submissions.
- **Submission lifecycle**: Candidate headers include token + session id → server ensures task belongs to session, correct order, and not yet submitted → submission stored; progress recalculated; session marked completed when final task done.
- **Execution profile (planned)**: `execution_profiles` table exists and `hasReport` flag surfaces in candidate listings, but no generation or AI evaluation is implemented yet.

## Future Work / Gaps

- Hook sandbox/test runner to populate `tests_passed/tests_failed/test_output`.
- Implement AI evaluation/report generation to create `ExecutionProfile` records and expose report data.
- Candidate authentication beyond bearer token possession (optional).
- Audit logging/analytics; richer task content (starter code paths/tests currently unused).
