# Phase 1 Sign-Off — tase-intel

> **Phase:** Phase 1 — Data Layer Infrastructure
> **Spec baseline:** V1.0.1
> **Sign-off date:** ____________
> **Signed by:** ____________ (owner)
> **Status:** PROPOSED FOR APPROVAL  →  ____________
> **Repo state at sign-off:** commit `21c4c0e`, tag `v1.0.1-seed`

---

## 1. Mission Recap

Phase 1 established the data layer infrastructure for the tase-intel trading
intelligence system. This covered: repository scaffolding, Alembic migration
framework, the full V1.0.1 schema (27 tables, 9 SQL functions, bitemporal
columns, immutability triggers, hypertables), smoke tests for schema
correctness, forbidden-pattern static analysis, CI via GitHub Actions, and
baseline trading calendar seed data.

Phase 1 explicitly did NOT include: data ingestion from any external source,
event tagging, feature computation, model training, decision-making logic, or
any form of live or paper trading. These are Phase 2+ work items, gated behind
this sign-off.

---

## 2. Batches Completed

| # | Batch                              | Tag             | Commit    | Verified |
|---|------------------------------------|-----------------|-----------|----------|
| 1 | Repo skeleton                      | `v1.0.1-spec`   | `08b4625` | ✓        |
| 2 | Alembic scaffold                   | `v1.0.1-batch2` | `08b4625` | ✓        |
| 3 | Initial schema migration           | `v1.0.1-schema` | `08b4625` | ✓        |
| 4 | Smoke tests                        | `v1.0.1-smoke`  | `c49d27d` | ✓        |
| 5 | Forbidden-pattern lint             | `v1.0.1-lint`   | `a97d11d` | ✓        |
| 6 | CI / GitHub Actions                | `v1.0.1-ci`     | `79bd68c` | ✓        |
| 7 | Seed tase_trading_calendar         | `v1.0.1-seed`   | `21c4c0e` | ✓        |

**Note:** Batches 1–3 were combined into a single commit (`08b4625`) during
initial development. Tags `v1.0.1-spec` and `v1.0.1-batch2` were retroactively
created on this commit to complete the tag chain. All 7 batch tags are present.

---

## 3. Definition of Done — Verified

The following checklist is reproduced from `IMPLEMENTATION_GUARDRAILS_V1.0.1.md §5`.
Each item is verified against the repo's actual state at sign-off.

### 3.1 Migrations (§5.1)

- [x] All migrations in `src/migrations/` reviewed.
  *Evidence:* commits `08b4625` (V1.0.1.0001 baseline + V1.0.1.0002 schema)
  reviewed during Batch 3 Gate. Two migration files exist.
- [x] `alembic upgrade head` runs cleanly on a fresh DB.
  *Evidence:* CI workflow `ci.yml` runs this on every push against a fresh
  TimescaleDB service container; latest run green.
- [x] `alembic downgrade base` runs cleanly.
  *Evidence:* manually verified during Batch 3 Gate. CI does not currently
  exercise downgrade (forward-only). Acceptable for Phase 1.
- [x] `alembic upgrade head` after downgrade is idempotent.
  *Evidence:* manually verified during Batch 3 Gate (upgrade → downgrade →
  upgrade cycle).
- [x] All 27+ required tables exist with correct schema.
  *Evidence:* `tests/smoke/test_schema_integrity.py::test_all_required_tables_exist`
  passes in CI. DB confirms 28 tables (27 app + 1 alembic_version).
- [x] All 9 required SQL functions exist and are callable.
  *Evidence:* `tests/smoke/test_schema_integrity.py::test_all_required_functions_exist`
  passes in CI. DB confirms: `prices_daily_as_of`, `events_as_of`,
  `features_at_event_as_of`, `companies_as_of`, `macro_daily_as_of`,
  `intraday_quotes_summary_as_of`, `is_trading_day`, `subtract_trading_days`,
  `add_trading_days`.

### 3.2 Smoke Tests Pass (§5.2)

- [x] §4.1 schema integrity passes.
  *Evidence:* `test_schema_integrity.py` — 3 tests pass.
- [x] §4.4 decisions_log validation passes.
  *Evidence:* `test_check_constraints.py::TestDecisionsLogDecision` — 3 tests pass.
- [x] §4.5 raw immutability passes.
  *Evidence:* `test_raw_immutability.py` — 12 tests pass (4 tables × insert/update/delete).
- [x] §4.6 no same-day close passes.
  *Evidence:* `test_forbidden_patterns.py::test_no_same_day_close` passes.
- [x] §4.8 no as-of bypass passes.
  *Evidence:* `test_forbidden_patterns.py::test_no_bitemporal_bypass` passes.
- [x] CI runs all the above in under 5 minutes.
  *Evidence:* latest CI run completes full validate job (migrate + smoke + lint)
  in under 2 minutes.

### 3.3 Rollback Tested (§5.3)

- [x] `alembic downgrade -1` rolls back the most recent migration.
  *Evidence:* manually verified during Batch 3 Gate.
- [ ] No data loss in `raw_*` tables during downgrade.
  *NOT FULLY TESTED.* The downgrade drops all tables (including raw). This is
  acceptable for Phase 1 (no real data exists yet). In production, raw tables
  would need backup before downgrade. Documented in Section 6 (Limitations).
- [ ] `pg_dump` of staging executed and stored to backup location.
  *NOT APPLICABLE.* No staging environment exists in Phase 1. Local-only.
- [ ] `pg_restore` from backup verified on a separate DB.
  *NOT APPLICABLE.* Same as above.
- [ ] Recovery time documented.
  *NOT APPLICABLE.* No RTO established for local dev environment.

### 3.4 Seed Data Loaded (§5.4)

- [x] `tase_trading_calendar`: ≥5 years backward + 1 year forward populated.
  *Evidence:* `make seed-calendar` ran successfully. 2556 rows (2021-01-01 to
  2027-12-31): 1825 trading days, 731 non-trading days.
- [ ] `companies`: at least all current TA-35 + TA-90 members.
  *DEFERRED TO PHASE 2.* Requires entity resolution from TASE data sources.
- [ ] `index_membership_history`: TA-35 + TA-90 history ≥5 years.
  *DEFERRED TO PHASE 2.* Requires TASE index data ingestion.
- [ ] `macro_daily`: VIX, SP500, USDILS, BOI_RATE for last 5 years.
  *DEFERRED TO PHASE 2.* Requires FRED and BoI API integration.
- [ ] `prices_daily`: ≥1 month of TA-35 prices for verification.
  *DEFERRED TO PHASE 2.* Requires TASE EOD price ingestion.

### 3.5 No Forbidden Patterns in CI (§5.5)

- [x] CI lint job for `timedelta(days=N)` near "embargo" passes (zero matches).
  *Evidence:* `test_forbidden_patterns.py::test_no_calendar_day_embargo` passes.
- [x] CI lint job for `business_date = DATE(event_observable_at)` passes.
  *Evidence:* `test_forbidden_patterns.py::test_no_same_day_close` passes.
- [x] CI lint job for direct queries on bitemporal tables passes.
  *Evidence:* `test_forbidden_patterns.py::test_no_bitemporal_bypass` passes.
- [x] CI runs lint on every PR; blocks merge on failure.
  *Evidence:* branch protection rule on `main` requires `Validate (migrate +
  smoke + lint)` job to pass.

### 3.6 Documentation Locks (§5.6)

- [x] All four V1.0.1 spec docs under `docs/spec/`.
  *Evidence:* `TECHNICAL_CONTRACT_V1.0.1.md`, `DATA_LAYER_SPEC_V1.0.1.md`,
  `DECISION_MODEL_SPEC_V1.0.1.md`, `IMPLEMENTATION_GUARDRAILS_V1.0.1.md` all
  present.
- [x] Git tag `v1.0.1-spec` at the spec-finalization commit.
  *Evidence:* tag `v1.0.1-spec` points to `08b4625` (retroactively created).
- [x] Branch protection on `main`: requires CI green.
  *Evidence:* GitHub branch protection rule active; PR #1 (Batch 7) required
  passing CI before merge.
- [x] `README.md` at repo root with mission, disclaimer, quick start.
  *Evidence:* `README.md` exists with project description and spec links.

### 3.7 Sign-off (§5.7)

This document IS that sign-off.

---

## 4. System State at Sign-Off

### 4.1 Repository

- Commit: `21c4c0e`
- Latest tag: `v1.0.1-seed`
- Branch: `main`
- Branch protection: enabled (CI required, PR required for merge)

### 4.2 Schema

- Alembic head: V1.0.1.0002
- Revision hash: `d8ee463a3c6b`
- Tables in public schema: 28 (27 application + 1 alembic_version)
- Functions in public schema: 9 application + 2 trigger functions
  (+ ~80 TimescaleDB internal functions)
- Hypertables: 2 (`prices_daily`, `features_daily`)
- Triggers: 10 (raw immutability on 4 tables × UPDATE/DELETE + 2 validation)

### 4.3 Tests

- Smoke tests: 58 passing
- Lint tests: 16 passing (3 real-repo + 13 self-tests)
- Total: 74
- CI runtime (latest): ~2 minutes

### 4.4 Tooling Versions

- Python: ≥3.11 (per `pyproject.toml`; local dev: 3.14.3; CI: 3.11)
- Postgres + TimescaleDB: `timescale/timescaledb:2.14.2-pg15`
- Alembic: 1.18.4
- pytest: 8.4.2
- psycopg: 3.3.3
- CI runner: `ubuntu-22.04`

### 4.5 Seed Data

- `tase_trading_calendar`: 2556 rows (1825 trading, 731 non-trading)
  - Range: 2021-01-01 to 2027-12-31
  - Pattern: Sun–Thu = trading, Fri–Sat = non-trading
  - Holidays: NOT handled (see Section 6.2)
- All other tables: empty (deferred to Phase 2)

---

## 5. Capabilities at Sign-Off

The system at this point provides:

- A bitemporally-correct schema for prices, events, features, decisions, and
  audit/lineage data, per V1.0.1 spec.
- A trading-day calendar covering 7 years (2021–2027), with Sunday–Thursday
  marked as trading days. **Note: Israeli holidays are not yet handled** — a
  Yom Kippur or Pesach falling on Sun–Thu is currently mis-marked as a trading
  day. This is documented as a known limitation (Section 6.2).
- Static enforcement of three forbidden code patterns (calendar-day embargo,
  same-day-close reference, bitemporal table bypass) via custom lint.
- Schema integrity, constraint, immutability, CI-ordering, and as-of correctness
  verified by 58 smoke tests.
- CI on every push and PR via GitHub Actions; `main` branch protected.

The system at this point does NOT:

- Ingest any data from external sources (TASE, MAYA, news RSS, FRED, BoI).
- Tag any events.
- Compute any features.
- Train any model.
- Make any decisions.
- Trade with any money, real or paper.

These are Phase 2+ work, intentionally out of Phase 1 scope.

---

## 6. Known Limitations & Deferred Work

### 6.1 Seed data — partial

`IMPLEMENTATION_GUARDRAILS §5.4` lists several seed items. Phase 1 completed
only the trading calendar. The following are deferred to Phase 2:

- `companies` (current TA-35 + TA-90 members)
- `index_membership_history` (5-year history of index membership changes)
- `macro_daily` (VIX, SP500, USDILS, BOI_RATE)
- `prices_daily` (≥1 month for verification)

### 6.2 Trading calendar — no holidays

V1.0.1's seed marks Sunday–Thursday as `is_trading_day = TRUE` and
Friday–Saturday as `FALSE`. It does NOT handle Israeli holidays. A Yom Kippur
falling on Sunday–Thursday is currently mis-classified as a trading day.

This is acceptable for Phase 1 sign-off because no model or backtest is using
the calendar yet. **Before any backtest or paper trading begins, this must be
addressed.** The planned approach is a separate `seed_holidays.py` script that
overlays `is_trading_day = FALSE` on known holiday dates, run after
`seed_calendar.py`.

### 6.3 Local-only environment

V1.0.1 runs locally via Docker on the developer's machine. There is no staging
environment, no production environment, no shared dev DB. This means:

- No multi-user collaboration on the DB.
- No backup discipline beyond manual `pg_dump` runs.
- Recovery scenarios from `DATA_LAYER_SPEC §10` are documented but only partly
  rehearsed (basic downgrade drill done; full disaster recovery not).

### 6.4 Migration downgrade not in CI

CI runs `alembic upgrade head` on every push but does not run a full downgrade
cycle. The downgrade was manually verified during Batch 3 Gate but is not
continuously regression-tested. If a future migration breaks downgrade behavior,
CI will not catch it.

Deferred fix: add a `make migrate-roundtrip` target (upgrade → downgrade →
upgrade) and optionally a CI job that exercises it.

### 6.5 Manual smoke verification not automated

`IMPLEMENTATION_GUARDRAILS §4` references manual breaking of tests to confirm
they catch failures. This was performed during each batch's Gate (documented in
batch summaries) but is not automated. As the test suite grows, mutation testing
(e.g., `mutmut`) could ensure tests don't become vacuous. Not blocking for
Phase 2.

### 6.6 Rollback data preservation untested

The migration's `downgrade()` function drops all tables, including `raw_*`
tables. In production, this would destroy immutable audit data. This is
acceptable in Phase 1 (no real data exists), but before any data is ingested,
the downgrade strategy must be revised to preserve raw tables or require
explicit backup before downgrade.

---

## 7. Phase 2 Authorization

### 7.1 Phase 2 Scope (preview)

Phase 2 will introduce data ingestion: TASE EOD prices, MAYA/MAGNA filings,
news RSS, and macro data (FRED, BoI). It will populate the curated tables
that Phase 1 built but left empty.

Per the Technical Contract §1 and Data Layer Spec roadmap (§14), Phase 2
covers:

- TASE EOD ingestion + reconciliation against EODHD as fallback.
- MAYA scraper + `raw_filings` storage.
- News RSS poller + `raw_news` storage.
- Macro daily ingestion (FRED + BoI APIs).
- Entity resolution: filling `companies` table for active and recently
  delisted TA-35/TA-90 members.
- Holiday calendar overlay (addressing limitation §6.2).
- Remaining seed data (companies, index membership, macro, prices).

Phase 2 does NOT include:

- Event tagging (Phase 3 — NLP pipeline).
- Feature computation (Phase 3+).
- Model training (Phase 4).
- Memory layer (Phase 5).
- Paper trading (after all of the above).

### 7.2 Authorization

By signing this document below, the owner certifies:

- [ ] All items in Section 3 (Definition of Done) are either complete (✓) or
      explicitly listed as deferred in Section 6.
- [ ] The known limitations in Section 6 are acceptable for Phase 1 closure.
- [ ] The repository state described in Section 4 is the canonical V1.0.1
      baseline.
- [ ] No further changes will be made under the V1.0.1 banner without an
      amendment (per `TECHNICAL_CONTRACT §10` change protocol).
- [ ] Phase 2 work may begin, scoped per Section 7.1.

### 7.3 Discipline carry-forward to Phase 2

The same discipline that produced V1.0.1 must continue:

- Spec docs are the source of truth. Changes go through amendments.
- Each Phase 2 batch is small, gated, and reviewed before the next begins.
- CI must remain green throughout. A red `main` branch blocks Phase 2 progress.
- The forbidden-pattern lint catches new drift; do not weaken its rules to
  accommodate ingestion code.
- New tables or schema changes require a spec amendment first.

### 7.4 Signature

```
Owner:            ____________________   Date: __________
Status:           PROPOSED FOR APPROVAL  →  ____________
Phase 2 may begin: yes / no
```

---

**END OF PHASE 1 SIGN-OFF**
