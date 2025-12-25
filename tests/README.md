## Test architecture

- Layout: `tests/api` (route-level), `tests/unit` (pure functions), `tests/integration` (full flows through DB + services), `tests/property` (Hypothesis properties), `tests/factories` (async model factories), shared fixtures in `tests/conftest.py`.
- Fixtures: `async_client` wires FastAPI with dependency overrides; `db_session`/`async_session` share a truncated DB per test; `auth_header_factory` builds recruiter headers; `candidate_header_factory` builds candidate headers for task submissions.
- Factories: `tests/factories` exposes helpers to create companies, recruiters, simulations + seeded tasks, candidate sessions, and submissions without repeating boilerplate.
- Progress helpers: `app/utils/progress.py` centralizes current task and progress calculations and is unit/property tested.

## Running tests

- Standard run: `poetry run pytest`
- With coverage (CI default): `poetry run pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90`
- Property tests use Hypothesis; keep them in `tests/property` to toggle with `-k property` when needed.
