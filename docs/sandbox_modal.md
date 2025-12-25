# Sandbox (Modal) Integration

This backend talks to a Modal-hosted sandbox adapter that executes tests for candidate code.

## Deploying the Modal adapter

```code
modal secret create simuhire-sandbox-auth AUTH_TOKEN="<token>"
modal deploy sandbox_adapter/modal_app.py
```

The adapter exposes:

- `POST /run`
- `GET /health`

Both require `Authorization: Bearer <token>` matching the Modal secret.

## Backend environment

Set these variables (Render/local):

```code
SANDBOX_API_URL=https://robelk1738--simuhire-sandbox-adapter-fastapi-app.modal.run
SANDBOX_API_KEY=<AUTH_TOKEN>
SANDBOX_TIMEOUT_SECONDS=30
SANDBOX_POLL_INTERVAL_SECONDS=0.5
SANDBOX_MAX_POLL_SECONDS=20
```

## Manual QA (Postman or curl)

Request: `POST /api/tasks/{task_id}/run`

Headers:

- `x-candidate-token: <candidate_invite_token>`
- `x-candidate-session-id: <candidate_session_id>`
- `Content-Type: application/json`

Body example:

```json
{
  "codeBlob": "console.log('hi from candidate');"
}
```

Expected 200 response:

```json
{
  "status": "passed",
  "passed": 3,
  "failed": 0,
  "total": 3,
  "stdout": "All tests passed",
  "stderr": "",
  "timeout": false
}
```

Errors from the sandbox are surfaced as `502` with `{"detail": "Sandbox unavailable. Please try again."}`; no sandbox credentials or code are logged.

Task reference format sent to the sandbox:

- `<scenarioPrefix>-day<index>-<type>`
- `scenarioPrefix` comes from `simulation.scenario_template` (fallback to `focus`, else `default`), lowercased with spaces -> `-`.
- `day` is 1-based; if a task day is stored 0-based it is normalized by +1.
