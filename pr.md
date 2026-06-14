# Task 3: Harden AI pipeline integrity, citation resolution, validator enforcement, and demo QA seeds

## Summary

This PR completes the backend trust spine for Task 3: AI Pipeline Integrity. It adds model/provider preflight, explicit model and capability validation, a richer Citation API, Evidence Trail target resolution, validator enforcement for cited scoring evidence, Winoe persona/SOUL prompt assembly coverage, AgentSnapshot/fairness preservation, Winoe evaluation state-machine coverage, and deterministic demo/Task 3 seed data for the required QA credentials.

The backend changes keep Winoe evidence-first. Winoe provides evidence for the Talent Partner to decide; it does not make hiring decisions.

## Why this matters

Winoe AI cannot be trusted if Winoe Scores lack defensible Evidence Trail support. Every score needs to be tied to real artifacts, Talent Partners need to inspect the resolved targets, and Candidate access must remain denied for Talent Partner-only reports and artifacts.

The deterministic seed path also matters for YC/demo QA. QA should not depend on fragile local database state, drifting ownership, invalid local emails, or cleanup failures.

## Backend changes

### A. Model preflight / provider capability integrity

- Adds `app/ai/ai_model_preflight_service.py` and `scripts/verify_models.py`.
- Verifies configured models are reachable through the production provider paths.
- Makes capability validation explicit for `structured_json` and `transcription`.
- Covers OpenAI structured JSON probes, Anthropic structured JSON probes, and OpenAI transcription probes.
- Rejects blank primary/fallback model config and unsupported fallback provider config.
- Sanitizes provider failure summaries so API keys/secrets are not printed.
- Pins/documents the model matrix used by reviewer, Winoe, scenario generation, and transcription roles.

### B. Citation API / Evidence Trail resolution

- Extends the Winoe Report citation payload with `citation_id`, `dimension`, `artifact_range`, and `resolved_open_target`.
- Resolves `resolved_open_target` and `view_url` to real `/api/submissions/{id}` targets.
- Stops emitting fake `/view?...` target shapes.
- Preserves line/timestamp metadata in `artifact_range`.
- Expands target coverage across design doc, code implementation, transcript, and reflection artifacts.

### C. Validator enforcement

- Rejects dimensional scoring evidence without citations.
- Rejects dimensional scoring evidence with only unresolved/non-resolving citations.
- Keeps the valid cited evidence path accepted.

### D. Persona/SOUL governance

- Verifies Winoe prompt assembly includes persona/SOUL content.
- Keeps Winoe evidence-first.
- Preserves the boundary that Winoe does not make hiring decisions.
- Keeps evidence with Winoe and the decision with the Talent Partner.

### E. AgentSnapshot / fairness

- Confirms candidates in the same Trial use pinned agent/rubric/model snapshots.
- Preserves the fairness architecture by avoiding live prompt-pack drift during reruns.

### F. Evaluation state-machine

State-machine coverage now verifies the ordered Task 3 path:

- `REVIEWERS_DISPATCHED`
- `REVIEWERS_COMPLETE`
- `WINOE_SYNTHESIZING`
- `EVIDENCE_TRAIL_VALIDATING`
- `REPORT_FINALIZED`
- `NOTIFICATION_SENT`

### G. Demo / Task 3 seed reliability

- Keeps `seed_demo.sh` idempotent.
- Keeps `seed_task3_qa.py` idempotent.
- Aligns the required Talent Partner with the seeded Winoe Report company.
- Ensures the required Candidate exists as a backend candidate user.
- Avoids `.local.test` validation failures by using valid example-domain addresses.
- Avoids FK cleanup failure.
- Keeps candidate listing returning 200.
- Prevents seed ownership drift across repeated runs.

## Security / authorization

- No authorization checks were weakened.
- The required Talent Partner can access only company-owned Winoe Report, citation, and submission resources.
- Candidate remains denied from Talent Partner-only Winoe Report, Citation API, and submission targets.
- Unauthenticated access remains denied.
- Provider secrets are not printed in preflight output.

## QA evidence

```text
Model preflight: PASS
Seed sequence:
- ./scripts/seed_demo.sh: PASS
- ./scripts/seed_demo.sh: PASS
- poetry run python3 scripts/seed_task3_qa.py --talent-partner-email winoetalentpartner@gmail.com: PASS
- poetry run python3 scripts/seed_task3_qa.py --talent-partner-email winoetalentpartner@gmail.com: PASS

Backend server: PASS at http://127.0.0.1:8000
Backend health: GET /health -> 200 {"status":"ok"}
Talent Partner E2E: PASS
Candidate boundary: PASS
Citation API: PASS
Citation count: 15
Unique citation targets: 4
Citation targets: 4/4 unique targets returned 200 for Talent Partner, 403 for Candidate, 401 for unauthenticated
Validator tests: PASS
Persona/SOUL tests: PASS
AgentSnapshot/fairness tests: PASS
State-machine coverage: PASS
Backend local checks: PASS, 2233 passed, coverage 96.16%
```

## Citation verification table

| Artifact | Ref | Range | Target | Talent Partner | Unauth | Candidate |
|---|---|---:|---|---:|---:|---:|
| Design doc | `day1-design-doc.md:L1-L20` | `L1-L20` | `/api/submissions/85` | 200 | 401 | 403 |
| Code implementation | `857cd1e...:src/services/reporting.py:L12-L76` | `L12-L76` | `/api/submissions/87` | 200 | 401 | 403 |
| Transcript | `[00:00-02:00]` | `00:00-02:00` | `/api/submissions/88` | 200 | 401 | 403 |
| Reflection | `day5-reflection.md:L1-L18` | `L1-L18` | `/api/submissions/89` | 200 | 401 | 403 |

All citation targets use `/api/submissions/{id}`. No citation target includes `/view`. `artifact_range` preserves line/timestamp ranges.

## Test plan

```bash
poetry run python3 scripts/verify_models.py

./scripts/seed_demo.sh
./scripts/seed_demo.sh
poetry run python3 scripts/seed_task3_qa.py --talent-partner-email winoetalentpartner@gmail.com
poetry run python3 scripts/seed_task3_qa.py --talent-partner-email winoetalentpartner@gmail.com

poetry run pytest --no-cov \
  tests/ai/test_ai_model_preflight_service.py \
  tests/ai/test_ai_provider_clients_service.py \
  tests/evaluations/services/test_evaluations_evidence_trail_validator_service.py \
  tests/evaluations/routes/test_evaluations_winoe_report_citations_routes.py \
  tests/evaluations/services/test_evaluations_trial_evaluator_service.py \
  tests/evaluations/services/test_evaluations_evaluator_runner_service.py \
  tests/trials/services/test_trials_service_trial_agent_snapshots_service.py \
  tests/demo/services/test_demo_yc_seed_service.py \
  tests/demo/services/test_demo_task3_local_qa_seed_service.py \
  -q

./precommit.sh
```

Observed results:

- Targeted backend pytest: `102 passed`
- Backend local checks: `2233 passed`, coverage `96.16%`

## Manual QA

Backend server command:

```bash
WINOE_ENV=local DEV_AUTH_BYPASS=1 WINOE_DEV_AUTH_BYPASS=1 poetry run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

Manual QA covered:

- Talent Partner completed dashboard -> Trial detail -> Winoe Report path passed.
- Winoe Report rendered Winoe Score, all 8 dimensions/sub-scores, and evidence controls.
- Citation API returned 200 for Talent Partner.
- Talent Partner citation target requests returned 200.
- Candidate citation target requests returned 403.
- Unauthenticated citation target requests returned 401.
- Candidate portal rendered.
- Candidate was blocked from Talent Partner-only Winoe Report, Citation API, and submission artifacts.

## Risks / non-blocking notes

- No product risk was found in the Task 3 trust path.
- Local/dev hydration mismatch warnings were observed in browser QA.
- Existing frontend test-console warnings for React key/fake timer cleanup are outside backend PR scope.

## Rollback

Revert this PR to restore prior AI/evaluation/seed behavior. This branch diff does not add database migration files, so no database migration rollback is expected. If a migration is added before merge, document and run the exact downgrade for that migration.

## Reviewer checklist

- [ ] Model preflight is still green.
- [ ] Citation targets are real `/api/submissions/{id}` paths.
- [ ] No `/view` fake target is emitted.
- [ ] Candidate access is denied.
- [ ] Unauthenticated access is denied.
- [ ] Seeds are repeatable.
- [ ] Winoe persona does not decide hire/no-hire.
