<!--
PR Template — TASE Intel
Spec: V1.0.1
Reference: docs/spec/IMPLEMENTATION_GUARDRAILS_V1.0.1.md
-->

## What Changed

<!-- 1-3 sentences. What does this PR do? -->



## Why

<!-- What problem does this solve? Reference spec section if relevant. -->



## Type of Change

- [ ] Bug fix (no spec change)
- [ ] Implementation of existing spec (no spec change)
- [ ] CI / tooling / docs (no behavior change)
- [ ] Spec amendment (V1.0.X bump — must include `AMENDMENT_*.md`)

---

## Spec Compliance Checklist

**Read this list before submitting. Each ✓ should be deliberate.**

### Hard Constraints (Contract §7 / IMPLEMENTATION_GUARDRAILS §1)

- [ ] I have **not** changed the target formula (`forward_return_5d > total_costs × 1.5`).
- [ ] I have **not** added, removed, or modified any of the 12 model features.
- [ ] I have **not** changed bucket thresholds (market_cap_bucket, liquidity_bucket).
- [ ] I have **not** introduced `timedelta(days=N)` for embargo or trading-day arithmetic.
- [ ] I have **not** introduced LLM calls in the decision path.
- [ ] I have **not** changed the decision threshold (0.55 / 0.65) or CI rule (auto-skip if p10 < 0.5 < p90).
- [ ] I have **not** added interaction features manually.

### SQL / Data Layer (IMPLEMENTATION_GUARDRAILS §2)

- [ ] All curated table reads go through `*_as_of()` functions (no direct `SELECT` on `prices_daily`, `events`, `companies`, `features_at_event`, `macro_daily`, `corporate_actions`, `intraday_quotes_summary`).
- [ ] `features_at_event` writes include explicit `market_cap_bucket` and `liquidity_bucket` (no DEFAULT).
- [ ] No `UPDATE` or `DELETE` on `raw_*` tables.
- [ ] No `business_date = DATE(event_observable_at)` (same-day close = look-ahead).
- [ ] All new timestamp columns are `TIMESTAMPTZ`, not `TIMESTAMP`.
- [ ] All curated tables that may be retroactively corrected have `recorded_at` + `superseded_at`.

### Tests

- [ ] All existing tests pass locally (`make smoke-test && make lint`).
- [ ] If this PR adds behavior, I added tests for it.
- [ ] If this PR touches feature/target/embargo logic, the relevant tests in `tests/smoke/` still cover the case.
- [ ] No tests marked `xfail` or `skip` to bypass failure.

---

## Common Pitfalls Self-Check

**8 ways projects like this fail. Confirm none apply:**

- [ ] **#1 — "I'll fix it later."** I did not introduce a `WHERE business_date = DATE(event_observable_at)` "to make it run for now."
- [ ] **#2 — "Calendar days are close enough."** Embargo and any trading-day arithmetic uses `tase_trading_calendar` via `subtract_trading_days` / `add_trading_days`.
- [ ] **#3 — "I'll compute the bucket in Python at query time."** Buckets are stored explicitly in `features_at_event` and computed by feature_builder once.
- [ ] **#4 — "The source corrected the value, so I'll UPDATE it."** I did not UPDATE any historical row. Corrections go through bitemporal supersede pattern.
- [ ] **#5 — "`events_as_of()` is slow, I'll query directly."** I did not bypass `*_as_of()` functions. If performance is an issue, I added an index instead.
- [ ] **#6 — "I'll add a column to a raw table."** Raw tables are immutable. New columns went to staging or curated.
- [ ] **#7 — "This test is wrong, I'll xfail it."** No test is marked `xfail`. Either fixed the code or wrote an amendment.
- [ ] **#8 — "LightGBM is better, let me make it Primary."** Architecture change = V2 amendment. Not a code PR.

---

## Spec Amendments (only if Type = Spec Amendment)

If this PR includes spec changes:

- [ ] `AMENDMENT_V1.0.X.md` is included with justification.
- [ ] All affected spec docs are bumped to V1.0.X.
- [ ] Owner sign-off received (commit comment from owner explicitly approving).
- [ ] If amendment is "substantive" (Contract §10.1): validation framework restart documented.

---

## Triggers — Did You Stop and Re-read Spec?

If you found yourself doing any of these during this PR, you should have stopped and re-opened the spec docs. Check if you actually did:

- [ ] N/A — none of these came up.
- [ ] I needed to add a column → I confirmed it's spec-aligned in `DATA_LAYER_SPEC §4`.
- [ ] I needed to change a hyperparameter → It's only `C` (LogReg) tuned on validation, per `DECISION_MODEL_SPEC §5.2`.
- [ ] A test failed → I fixed the code, not the test.
- [ ] I extended a window → I confirmed the window matches `DECISION_MODEL_SPEC §4.1`.

---

## Environment Validation

**Required for every PR that touches DB schema, migrations, or code that depends on either.** Confirm by running locally and pasting outputs in PR description if requested:

- [ ] `make migrate` runs cleanly on a fresh DB (no errors, no warnings).
- [ ] `make smoke-test` passes (exit code 0, all smoke tests green).
- [ ] **No schema drift vs `DATA_LAYER_SPEC_V1.0.1.md` §4.** Confirmed by:
  - `\dt` output matches the table list in `IMPLEMENTATION_GUARDRAILS §3` (25+ tables, no extras, no missing).
  - `\df` output matches the function list in `IMPLEMENTATION_GUARDRAILS §3` (9 functions).
  - No tables, columns, constraints, or indices exist in DB that are not in the spec.
  - No tables, columns, constraints, or indices exist in spec that are missing from DB.

If drift is detected:
- [ ] **Stop.** Do not merge.
- [ ] Document the drift in PR description.
- [ ] Decide: reconcile DB to spec (preferred) or amend spec (requires `AMENDMENT_*.md`).
- [ ] Resolve before merge.

For PRs that only touch docs, CI, or non-DB code: this section is N/A; check the box below instead.

- [ ] N/A — this PR does not touch DB schema, migrations, or code that depends on either.

---

## Review Notes

<!-- Anything special the reviewer should know? Edge cases? Performance considerations? -->



---

## Spec References

<!-- Link to specific sections you relied on -->

- TECHNICAL_CONTRACT_V1.0.1.md §___
- DATA_LAYER_SPEC_V1.0.1.md §___
- DECISION_MODEL_SPEC_V1.0.1.md §___
- IMPLEMENTATION_GUARDRAILS_V1.0.1.md §___

---

<!--
Reviewer reminder:
- If any of the boxes above is unchecked without explicit reason, request changes.
- If "Type" is "Spec amendment" but no AMENDMENT file present, request changes.
- If tests are marked xfail/skip without justification, request changes.
- If the PR description is empty or boilerplate, request changes.

Reviewer's own self-check:
- [ ] I read at least one spec section relevant to this PR.
- [ ] I verified the test coverage actually exercises the changed behavior.
- [ ] I left at least one substantive comment (not just "LGTM").
-->
