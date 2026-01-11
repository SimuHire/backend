# Codespaces + GitHub Actions Flow

Tenon now runs code tasks entirely on GitHub: template repositories per task, Codespaces for editing, and Actions for tests.

## Template repositories
 - Each code/debug task sets `tasks.template_repo` to `owner/name`, resolved from `simulations.template_key` (API: `templateKey`).
- The backend is the source of truth for this mapping (see `app/domains/tasks/template_catalog.py`); frontend should only pass the `templateKey`.
- Available template keys -> repos:
  - Backend: `python-fastapi`, `node-express-ts`, `node-nest-ts`, `java-springboot`, `go-gin`, `dotnet-webapi`
  - Web full-stack: `monorepo-nextjs-nest`, `monorepo-nextjs-fastapi`, `monorepo-react-express`, `monorepo-react-springboot`
  - Mobile: `mobile-fullstack-expo-fastapi`, `mobile-backend-fastapi`
  - ML: `ml-backend-fastapi`, `ml-infra-mlops`
- To add a new template: add to the catalog module, create a migration/backfill if needed, ensure the GitHub template repo has the Actions workflow.
- Workflow file: `TENON_GITHUB_ACTIONS_WORKFLOW_FILE` (e.g., `tenon-ci.yml`) must exist in each template.

## Template health check (admin)
- Requires `X-Admin-Key` header matching `TENON_ADMIN_API_KEY`.
- `GET /api/admin/templates/health?mode=static` validates each template repo's default branch, workflow file, and artifact contract (static).
- `POST /api/admin/templates/health/run` runs live dispatch + artifact validation (opt-in).
- Failures return per-template errors like `workflow_file_missing`, `workflow_run_not_success`, or `test_results_json_invalid_schema`.

CLI:
- Static check all: `poetry run python scripts/template_health_check.py --mode static --all`
- Live check all (bounded): `poetry run python scripts/template_health_check.py --mode live --all --concurrency 2 --timeout-seconds 180`

## Candidate flow (backend endpoints)
0) `POST /api/simulations/{simulationId}/invite`
   - Creates Day 2/Day 3 workspace repos from task templates (idempotent per simulation + invite email).
1) `POST /api/tasks/{taskId}/codespace/init`
   - Creates repo from template; invites candidate via GitHub username.
   - Returns repo URL + Codespaces URL, default branch, workspace id, and stores `base_template_sha` (default branch head).
2) `POST /api/tasks/{taskId}/run`
   - Triggers `workflow_dispatch` on the workspace repo with optional `workflowInputs` + `branch`.
   - Polls the dispatched run and parses artifacts; returns `{status, passed, failed, total, stdout, stderr, runId, workflowUrl, commitSha}`.
3) `GET /api/tasks/{taskId}/run/{runId}`
   - Fetches an existing run result (polling helper) and returns the same normalized payload.
4) `POST /api/tasks/{taskId}/submit`
   - Triggers run (if needed) and stores commit/workflow ids, test output, and `diff_summary_json` from `base_template_sha...head_sha`.

Recruiter endpoints include repo/commit/workflow/diff URLs for detail and list views.

## Artifact contract (Actions -> Backend)
- Preferred artifact names (case-insensitive): `tenon-test-results`, `test-results`, `junit`.
- Artifact zip should contain `tenon-test-results.json` shaped as:
  ```json
  { "passed": 3, "failed": 1, "total": 4, "stdout": "...", "stderr": "", "summary": {...} }
  ```
- Fallback: any JSON with `passed/failed/total`; else JUnit XML (counts tests).

## Required environment
- `TENON_GITHUB_API_BASE` (default `https://api.github.com`)
- `TENON_GITHUB_ORG`
- `TENON_GITHUB_TOKEN` (bot/app token with repo + actions)
- `TENON_GITHUB_TEMPLATE_OWNER`
- `TENON_GITHUB_ACTIONS_WORKFLOW_FILE`
- `TENON_GITHUB_REPO_PREFIX`

## YC demo checklist
- Create/verify template repos for each task with the correct workflow file.
- Ensure Actions workflow uploads the artifact described above.
- Configure env vars (above) and restart backend.
- Run candidate flow end-to-end: init codespace, run tests, submit; verify recruiter list/detail show repo/commit/workflow/diff links and parsed test counts.
