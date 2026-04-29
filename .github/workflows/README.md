# CI Workflow

The `ci.yml` workflow validates the tase-intel schema on every push and PR to `main`.

## What it runs

1. **Migrate** — `alembic upgrade head` against a fresh TimescaleDB instance.
2. **Smoke tests** — `pytest tests/smoke/` verifies schema integrity, constraints, triggers, and as-of logic.
3. **Lint** — `pytest tests/lint/` scans for forbidden code patterns (IMPLEMENTATION_GUARDRAILS §4).

## Environment

- **Runner:** `ubuntu-22.04` (pinned)
- **Python:** `3.11` (matches `pyproject.toml`)
- **Database:** `timescale/timescaledb:2.14.2-pg15` (matches local `docker-compose.yml`)

The CI service container mirrors local Docker Compose — same image, same DB config.

## Debugging a failure

1. Check which step failed in the Actions UI.
2. If migration or smoke tests failed, expand the **Capture state on failure** step for DB diagnostics.
3. Reproduce locally: `make up && make migrate && make smoke-test && make lint`.

## Spec reference

- `docs/spec/IMPLEMENTATION_GUARDRAILS_V1.0.1.md` §4 (CI requirements), §5.5 (CI on every PR)
