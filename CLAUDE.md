# CLAUDE.md — Project Operating Rules

## Project: tase-intel

This is a production-grade AI trading intelligence system.

## Architecture Authority

The following documents are the single source of truth:

* docs/spec/TECHNICAL_CONTRACT_V1.0.1.md
* docs/spec/DATA_LAYER_SPEC_V1.0.1.md
* docs/spec/DECISION_MODEL_SPEC_V1.0.1.md
* docs/spec/IMPLEMENTATION_GUARDRAILS_V1.0.1.md

You MUST follow them strictly.

## Development Rules

1. Do NOT change architecture decisions.
2. Do NOT introduce new features without approval.
3. Do NOT skip batches.
4. Do NOT write SQL unless explicitly instructed (Batch 3).
5. Do NOT modify raw_* tables (immutable).
6. Always follow as-of logic (no leakage).
7. No LLM in decision path.

## Workflow

Batch 1 — Repo skeleton
Batch 2 — Alembic init
Batch 3 — Initial schema
Batch 4 — Smoke tests
Batch 5 — Lint
Batch 6 — CI
Batch 7 — Seed data
Batch 8 — Phase completion

Never skip a batch.

## Output Format

* Show file path
* Show full content
* No partial snippets
* No explanations unless asked

## If uncertain

STOP and ask. Do not guess.
