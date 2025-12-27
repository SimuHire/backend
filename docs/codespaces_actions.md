# Codespaces + GitHub Actions Flow

SimuHire now runs code tasks entirely on GitHub: template repositories per task, Codespaces for editing, and Actions for tests.

## Template repositories
- Each code/debug task sets `tasks.template_repo` to `owner/name`.
- The backend is the source of truth for this mapping (seeded via migrations/fixtures).
- Workflow file: `GITHUB_ACTIONS_WORKFLOW_FILE` (e.g., `simuhire-ci.yml`) must exist in each template.

## Candidate flow (backend endpoints)
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
- Preferred artifact names (case-insensitive): `simuhire-test-results`, `test-results`, `junit`.
- Artifact zip should contain `simuhire-test-results.json` shaped as:
  ```json
  { "passed": 3, "failed": 1, "total": 4, "stdout": "...", "stderr": "", "summary": {...} }
  ```
- Fallback: any JSON with `passed/failed/total`; else JUnit XML (counts tests).

## Required environment
- `GITHUB_API_BASE` (default `https://api.github.com`)
- `GITHUB_ORG`
- `GITHUB_TOKEN` (bot/app token with repo + actions)
- `GITHUB_TEMPLATE_OWNER`
- `GITHUB_ACTIONS_WORKFLOW_FILE`
- `GITHUB_REPO_PREFIX`

## YC demo checklist
- Create/verify template repos for each task with the correct workflow file.
- Ensure Actions workflow uploads the artifact described above.
- Configure env vars (above) and restart backend.
- Run candidate flow end-to-end: init codespace, run tests, submit; verify recruiter list/detail show repo/commit/workflow/diff links and parsed test counts.
