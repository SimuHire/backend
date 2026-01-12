# Tenon Backend

FastAPI + Postgres backend for Tenon. Recruiters create 5-day simulations, invite candidates, and review GitHub-native task submissions. Candidates work entirely in GitHub (template repos + Codespaces + Actions) and authenticate via Auth0 access tokens tied to their invites.

## GitHub-Native Execution

- Template catalog source of truth: `app/domains/tasks/template_catalog.py` maps `templateKey` → template repo (`owner/name`). Code/debug tasks pull their template from the simulation’s `templateKey`.
- Workflow expectations: `TENON_GITHUB_ACTIONS_WORKFLOW_FILE` must exist in each template repo and support `workflow_dispatch`. Artifact contract: preferred artifact name `tenon-test-results` (case-insensitive) containing `tenon-test-results.json` with `{passed, failed, total, stdout, stderr, summary?}`. Fallback: any JSON with those keys, else JUnit XML.
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
- Data model highlights: `Simulation` → `Task` (5-day blueprint seeded on create); `Simulation` → `CandidateSession` (token, status, timestamps, expires_at); `CandidateSession` → `Submission` (one per task, stores code repo/run/diff/test info); `CandidateSession` → `Workspace` (GitHub repo metadata, last run info); `FitProfile` placeholder for future reports.

## Domain Glossary

- Simulation: recruiter-owned scenario with role/techStack/focus/templateKey.
- Task: daily assignment; type drives validation (`design`, `code`, `debug`, `handoff`, `documentation`).
- Candidate Session: invite for a candidate; secured by invite token + Auth0 identity; tracks progress/expiry.
- Workspace: GitHub repo generated from template for a candidate+task; stores last Actions results.
- Submission: final turn-in for a task with optional test results and diff summary.
- Fit Profile: planned evaluation/report entity (model exists; no generation).

## API Overview

- Health: `GET /health`
- Auth: `GET /api/auth/me` (Auth0 or dev bypass)
- Recruiter (Auth0/dev bypass; recruiter role):
  - `GET /api/simulations` list owned (with candidate counts)
  - `POST /api/simulations` create + seed 5 tasks (uses `templateKey`)
  - `POST /api/simulations/{id}/invite` create candidate token/link
  - `GET /api/simulations/{id}/candidates` list sessions (`hasFitProfile` if `fit_profiles` row)
  - `GET /api/submissions` list submissions (filters `candidateSessionId`, `taskId`)
  - `GET /api/submissions/{id}` detail with content/code/test results + repo/commit/workflow/diff URLs
- Admin (X-Admin-Key):
  - `GET /api/admin/templates/health` static validate template repos and workflow file
  - `POST /api/admin/templates/health/run` live dispatch + artifact validation (opt-in)
- Candidate (Auth0 access token + invite token):
  - `POST /api/candidate/session/{token}/verify` (Auth0 `Authorization: Bearer <access_token>`) claims invite for the logged-in candidate and transitions to in-progress
  - `GET /api/candidate/session/{token}` same as verify (idempotent claim/bootstrap with Auth0 identity)
  - `GET /api/candidate/session/{id}/current_task` (Auth0 bearer + `x-candidate-session-id` optional) current task/progress; auto-completes when done
  - `POST /api/tasks/{taskId}/codespace/init` (Auth0 bearer) create/return workspace repo + Codespace URL (code/debug tasks)
  - `GET /api/tasks/{taskId}/codespace/status` (Auth0 bearer) workspace state (repo/default branch/latest run/test summary)
  - `POST /api/tasks/{taskId}/run` (Auth0 bearer) trigger Actions tests; returns normalized run result
  - `GET /api/tasks/{taskId}/run/{runId}` (Auth0 bearer) fetch prior run result
  - `POST /api/tasks/{taskId}/submit` (Auth0 bearer) submit task (runs tests for code tasks, stores run/diff/test info)
- Errors: 401 missing candidate headers; 400 invalid branch/non-code run/no workspace; 404/410 invalid/expired token; 409 duplicate submission or completed simulation; 429 prod rate limit; 502 GitHub failure.

## Typical Flow

1. Recruiter authenticates → `POST /api/simulations` → `POST /api/simulations/{id}/invite` to generate candidate link.
2. Candidate opens invite while logged in via Auth0 → claims invite (email match required) → sees current task → for code/debug tasks calls `/codespace/init` → works in Codespace → `/run` to test → `/submit` to turn in.
3. Recruiter views submissions list/detail with repo/workflow/commit/diff/test results.

## Local Development

- Prereqs: Python 3.11+, Poetry, Postgres (or SQLite fallback).
- Install: `poetry install`; configure `.env` (sample included—rotate secrets).
- Seed dev recruiters: `ENV=local DEV_AUTH_BYPASS=1 poetry run python scripts/seed_local_recruiters.py`.
- Run: `poetry run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000` or `./runBackend.sh`.
- Migrations: `poetry run alembic upgrade head` (uses `DATABASE_URL_SYNC`).
- Tests: `poetry run pytest` (property tests under `tests/property`).
- Dev auth: set `DEV_AUTH_BYPASS=1` and send header `x-dev-user-email: recruiter1@local.test` for recruiter endpoints; candidate endpoints require Auth0 bearer tokens (tests may still use `x-candidate-session-id` helper headers).

## Template Health Checks

- Admin API: `X-Admin-Key: <TENON_ADMIN_API_KEY>` required.
- Static check: `GET /api/admin/templates/health?mode=static`
- Live check: `POST /api/admin/templates/health/run` with `{ "templateKeys": [...], "mode": "live", "timeoutSeconds": 180 }`
- CLI static all: `poetry run python scripts/template_health_check.py --mode static --all`
- CLI live all: `poetry run python scripts/template_health_check.py --mode live --all --concurrency 2 --timeout-seconds 180`

## Configuration

- DB: `TENON_DATABASE_URL`, `TENON_DATABASE_URL_SYNC` (sync used by Alembic; async derived automatically; SQLite fallback `local.db` if unset).
- Auth0: `TENON_AUTH0_DOMAIN`, `TENON_AUTH0_ISSUER`, `TENON_AUTH0_JWKS_URL`, `TENON_AUTH0_API_AUDIENCE`, `TENON_AUTH0_ALGORITHMS`, `TENON_AUTH0_CLAIM_NAMESPACE`, `TENON_AUTH0_EMAIL_CLAIM`, `TENON_AUTH0_ROLES_CLAIM`, `TENON_AUTH0_PERMISSIONS_CLAIM`.
- Auth0 Post Login Action must set `https://tenon.ai/permissions` (and `permissions`) on both access and ID tokens so first-login candidates receive `candidate:access`.
- CORS: `TENON_CORS_ALLOW_ORIGINS` (JSON array or comma list), `TENON_CORS_ALLOW_ORIGIN_REGEX`.
- Candidate portal: `TENON_CANDIDATE_PORTAL_BASE_URL` (used for invite links).
- GitHub: `TENON_GITHUB_API_BASE`, `TENON_GITHUB_ORG`, `TENON_GITHUB_TEMPLATE_OWNER`, `TENON_GITHUB_REPO_PREFIX`, `TENON_GITHUB_ACTIONS_WORKFLOW_FILE`, `TENON_GITHUB_TOKEN`, `TENON_GITHUB_CLEANUP_ENABLED` (future).
- Admin: `TENON_ADMIN_API_KEY` (required for admin endpoints).
- Dev bypass: `DEV_AUTH_BYPASS=1` (local only; app aborts otherwise).

## Roadmap (not implemented yet)

- Pre-provision repos at invite/simulation creation.
- Invite email notifications.
- AI scenario generation/evaluation + repo tailoring commits; generate `FitProfile` reports.
- Day4 media upload pipeline; Day5 structured documentation.
- Background jobs system.
- Repo cleanup post-eval.
- Webhook ingestion + GitHub App auth migration.
- Structured logging/monitoring/admin metrics; prod deploy plan and disabling dev bypass outside dev.
