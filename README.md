# SimuHire Backend

FastAPI + Postgres backend for SimuHire. Recruiters create 5-day simulations, invite candidates, and review GitHub-native task submissions. Candidates work entirely in GitHub (template repos + Codespaces + Actions) and authenticate via invite tokens.

## GitHub-Native Execution

- Template catalog source of truth: `app/domains/tasks/template_catalog.py` maps `templateKey` → template repo (`owner/name`). Code/debug tasks pull their template from the simulation’s `templateKey`.
- Workflow expectations: `GITHUB_ACTIONS_WORKFLOW_FILE` must exist in each template repo and support `workflow_dispatch`. Artifact contract: preferred artifact name `simuhire-test-results` (case-insensitive) containing `simuhire-test-results.json` with `{passed, failed, total, stdout, stderr, summary?}`. Fallback: any JSON with those keys, else JUnit XML.
- Flow: backend provisions a workspace repo from the template → returns Codespace URL → triggers/polls Actions runs → parses artifacts → stores run/test/diff metadata on `Workspace` and `Submission`. Diff summary computed via GitHub compare (base template SHA → head commit).

## Architecture

- FastAPI app factory `app/api/main.py` with CORS/proxy middleware; routers in `app/api/routes`.
- Infra: settings `app/infra/config.py`, env helpers `app/infra/env.py`, DB `app/infra/db` (async SQLAlchemy + SQLite fallback), security `app/infra/security/*` (Auth0 JWT + local dev bypass).
- Domains: `app/domains/*`
  - Simulations (`simulations/*`): model, create/list, invite creation.
  - Tasks (`tasks/*`): task model, template catalog, public schemas.
  - Candidate Sessions (`candidate_sessions/*`): token-based invites, progress helpers.
  - Submissions (`submissions/*`): submission model/services (candidate + recruiter), run/diff helpers, schemas, exceptions.
  - GitHub Native (`github_native/*`): REST client, Actions runner, artifact parsing, workspace model/repo.
  - Users/Companies (`users`, `companies`), Common types/schemas.
- Data model highlights: `Simulation` → `Task` (5-day blueprint seeded on create); `Simulation` → `CandidateSession` (token, status, timestamps, expires_at); `CandidateSession` → `Submission` (one per task, stores code repo/run/diff/test info); `CandidateSession` → `Workspace` (GitHub repo metadata, last run info); `ExecutionProfile` placeholder for future reports.

## Domain Glossary

- Simulation: recruiter-owned scenario with role/techStack/focus/templateKey.
- Task: daily assignment; type drives validation (`design`, `code`, `debug`, `handoff`, `documentation`).
- Candidate Session: invite for a candidate; secured by token; tracks progress/expiry.
- Workspace: GitHub repo generated from template for a candidate+task; stores last Actions results.
- Submission: final turn-in for a task with optional test results and diff summary.
- Execution Profile: planned evaluation/report entity (model exists; no generation).

## API Overview

- Health: `GET /health`
- Auth: `GET /api/auth/me` (Auth0 or dev bypass)
- Recruiter (Auth0/dev bypass; recruiter role):
  - `GET /api/simulations` list owned (with candidate counts)
  - `POST /api/simulations` create + seed 5 tasks (uses `templateKey`)
  - `POST /api/simulations/{id}/invite` create candidate token/link
  - `GET /api/simulations/{id}/candidates` list sessions (`hasReport` if `execution_profiles` row)
  - `GET /api/submissions` list submissions (filters `candidateSessionId`, `taskId`)
  - `GET /api/submissions/{id}` detail with content/code/test results + repo/commit/workflow/diff URLs
- Candidate (token headers):
  - `POST /api/candidate/session/{token}/verify` verify invite email, start session, issue short-lived candidate token
  - `GET /api/candidate/session/{token}` responds 401 (verification required; use `/verify`)
  - `GET /api/candidate/session/{id}/current_task` (header `x-candidate-token`) current task/progress; auto-completes when done
  - `POST /api/tasks/{taskId}/codespace/init` create/return workspace repo + Codespace URL (code/debug tasks)
  - `GET /api/tasks/{taskId}/codespace/status` workspace state (repo/default branch/latest run/test summary)
  - `POST /api/tasks/{taskId}/run` trigger Actions tests; returns normalized run result
  - `GET /api/tasks/{taskId}/run/{runId}` fetch prior run result
  - `POST /api/tasks/{taskId}/submit` submit task (runs tests for code tasks, stores run/diff/test info)
- Errors: 401 missing candidate headers; 400 invalid branch/non-code run/no workspace; 404/410 invalid/expired token; 409 duplicate submission or completed simulation; 429 prod rate limit; 502 GitHub failure.

## Typical Flow

1) Recruiter authenticates → `POST /api/simulations` → `POST /api/simulations/{id}/invite` to generate candidate link.
2) Candidate opens invite → verifies email to get candidate token → sees current task → for code/debug tasks calls `/codespace/init` → works in Codespace → `/run` to test → `/submit` to turn in.
3) Recruiter views submissions list/detail with repo/workflow/commit/diff/test results.

## Local Development

- Prereqs: Python 3.11+, Poetry, Postgres (or SQLite fallback).
- Install: `poetry install`; configure `.env` (sample included—rotate secrets).
- Seed dev recruiters: `ENV=local DEV_AUTH_BYPASS=1 poetry run python scripts/seed_local_recruiters.py`.
- Run: `poetry run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000` or `./runBackend.sh`.
- Migrations: `poetry run alembic upgrade head` (uses `DATABASE_URL_SYNC`).
- Tests: `poetry run pytest` (property tests under `tests/property`).
- Dev auth: set `DEV_AUTH_BYPASS=1` and send header `x-dev-user-email: recruiter1@local.test` for recruiter endpoints; candidate endpoints use invite token + `x-candidate-token`/`x-candidate-session-id`.

## Configuration

- DB: `DATABASE_URL`, `DATABASE_URL_SYNC` (sync used by Alembic; async derived automatically; SQLite fallback `local.db` if unset).
- Auth0: `AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_JWKS_URL`, `AUTH0_API_AUDIENCE`, `AUTH0_ALGORITHMS`.
- CORS: `CORS_ALLOW_ORIGINS` (JSON array or comma list), `CORS_ALLOW_ORIGIN_REGEX`.
- Candidate portal: `CANDIDATE_PORTAL_BASE_URL` (used for invite links).
- GitHub: `GITHUB_API_BASE`, `GITHUB_ORG`, `GITHUB_TEMPLATE_OWNER`, `GITHUB_REPO_PREFIX`, `GITHUB_ACTIONS_WORKFLOW_FILE`, `GITHUB_TOKEN`, `GITHUB_CLEANUP_ENABLED` (future).
- Dev bypass: `DEV_AUTH_BYPASS=1` (local only; app aborts otherwise).

## Roadmap (not implemented yet)

- Pre-provision repos at invite/simulation creation.
- Invite email verification + notifications.
- AI scenario generation/evaluation + repo tailoring commits; generate `ExecutionProfile` reports.
- Day4 media upload pipeline; Day5 structured documentation.
- Background jobs system.
- Repo cleanup post-eval.
- Webhook ingestion + GitHub App auth migration.
- Structured logging/monitoring/admin metrics; prod deploy plan and disabling dev bypass outside dev.
