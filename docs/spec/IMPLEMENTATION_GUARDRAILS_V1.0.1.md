# IMPLEMENTATION GUARDRAILS V1.0.1

> **Purpose:** מנע סטייה מ-spec במהלך SQL/code writing. לקריאה מהירה — לא spec.
> **Audience:** developer יחיד, Claude Code, GitHub Copilot, כל reviewer.
> **Companion to:** `TECHNICAL_CONTRACT_V1.0.1.md`, `DATA_LAYER_SPEC_V1.0.1.md`, `DECISION_MODEL_SPEC_V1.0.1.md`.
> **When in doubt:** הספקים הם source of truth. המסמך הזה מסכם, לא מחליף.

---

## 1. אסור לשנות. נקודה.

ערכים אלה **קבועים**. כל סטייה ב-code = bug, לא feature.

### Target formula
```
target = 1 if forward_return_5d > total_costs × 1.5 else 0
total_costs = 0.0030 + (spread_pct × 2)
```
**אסור:** לכוונן את 1.5, לכוונן את 0.0030, להחליף את 5d ב-3d/7d/10d.

### Feature list (12, frozen + missing flags + auxiliary)
**Model features (12):** `event_type_l1`, `event_type_l2`, `event_magnitude`, `event_source_tier`, `market_cap_log`, `sector`, `liquidity_score`, `vix_level`, `ta35_trend`, `usdils_5d_change`, `recent_return_20d`, `volatility_20d`.
**Missing flags:** `event_magnitude_missing`.
**Auxiliary (in JSONB, NOT input to model):** `spread_pct`, `spread_is_synthetic`, `market_cap_ils`, `adv_20`.
**אסור:** להוסיף features (RSI, MACD, sentiment, P/E, beta, volume_anomaly, etc). אסור interaction features.

### Bucket thresholds
```
market_cap_bucket: large ≥ 9.5 | mid ≥ 8.5 | small < 8.5
liquidity_bucket:  large ≥ 0.7 | mid ≥ 0.4 | small < 0.4
```
**אסור:** להזיז thresholds. אסור להוסיף bucket רביעי.

### Embargo
**5 trading days. תמיד דרך `tase_trading_calendar`.**
**אסור:** `timedelta(days=5)`. אסור `5 * 1.5`. אסור business-day approximations.

### As-of discipline
**כל קריאה לdata curated עוברת דרך function `*_as_of()`.**
**אסור:** SELECT ישיר מ-`prices_daily`, `events`, `companies`, `features_at_event` בקוד אפליקטיבי.

### Decision threshold
```
take if p_point > 0.55 (or 0.65 if Memory insufficient)
auto-skip if p10 < 0.5 < p90 (CI crosses 0.5)
```
**אסור:** לכוונן thresholds על backtest. לעולם.

### No LLM in decision path
LLM משמש **רק** ל-(1) event tagging ו-(2) explanation. **לעולם לא** מקבל החלטה, קובע threshold, או מחשב probability.

### No live money in MVP
12 חודשי paper trading minimum. **אסור** execution אוטומטית, אפילו ב-paper.

---

## 2. SQL Implementation Rules

### 2.1 NO DEFAULT for buckets
```sql
-- ❌ WRONG
market_cap_bucket TEXT DEFAULT 'mid'

-- ✅ RIGHT — must be computed explicitly at insert time
market_cap_bucket TEXT NOT NULL CHECK (market_cap_bucket IN ('large','mid','small'))
```
Reason: silent default = silent bug ב-Memory queries.

### 2.2 NO `sample_size`/`effective_n` ב-prices_daily
ערכים אלה שייכים ל-Memory output, לא ל-prices. **אסור** להוסיף עמודות אלה ל-`prices_daily`, `events`, או `features_at_event`.

### 2.3 Raw tables = immutable
```sql
-- ❌ WRONG
UPDATE raw_price_snapshots SET ... ;
DELETE FROM raw_filings WHERE ... ;

-- ✅ RIGHT — append new ingestion record only
INSERT INTO raw_price_snapshots (...) VALUES (...);
```
Trigger לאכיפה ב-§4.5.

### 2.4 Curated reads דרך as-of בלבד
```sql
-- ❌ WRONG
SELECT close FROM prices_daily WHERE company_id = X AND business_date = Y;

-- ✅ RIGHT
SELECT close FROM prices_daily_as_of(NOW()) WHERE company_id = X AND business_date = Y;
-- or for backtest:
SELECT close FROM prices_daily_as_of(:as_of_timestamp) WHERE ...;
```

### 2.5 NO same-day close ב-event decisions
```sql
-- ❌ WRONG (look-ahead)
JOIN prices_daily p ON p.business_date = DATE(e.event_observable_at)

-- ✅ RIGHT
JOIN prices_daily p ON p.business_date = subtract_trading_days(DATE(e.event_observable_at), 1)
```
**Exception:** אם `event_observable_at` > 17:30 IST → same-day allowed. דורש explicit branch + comment + test coverage.

### 2.6 NO bare timestamps
```sql
-- ❌ WRONG
recorded_at TIMESTAMP

-- ✅ RIGHT
recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
```
כל timestamp ב-DB חייב להיות `TIMESTAMPTZ`, UTC-stored.

### 2.7 Bitemporal columns חובה
לכל curated table המצריכה תיקונים רטרואקטיביים:
```sql
recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
superseded_at TIMESTAMPTZ
```
חסר אחד מהם → לא ניתן לבצע retroactive correction ללא איבוד היסטוריה. ראה Data Layer §5.

### 2.8 UNIQUE constraints על raw tables
```sql
UNIQUE(source, ..., payload_hash)  -- enables idempotent re-ingestion
```
חסר → re-runs יוצרים duplicates.

---

## 3. Required DB Artifacts

לפני שכל code אפליקטיבי רץ, ה-artifacts הבאים חייבים להיות קיימים בDB. רשימת checklist לcheckin של schema migration:

### Tables
- [ ] `raw_price_snapshots`
- [ ] `raw_filings`
- [ ] `raw_news`
- [ ] `raw_macro`
- [ ] `staging_filings_parsed`
- [ ] `staging_news_tagged`
- [ ] `staging_prices_normalized`
- [ ] `companies` (with bitemporal columns)
- [ ] `company_tickers_history`
- [ ] `company_aliases`
- [ ] `index_membership_history`
- [ ] `prices_daily` (TimescaleDB hypertable)
- [ ] `corporate_actions`
- [ ] `intraday_quotes_summary` ← **חדש ב-V1.0.1**
- [ ] `events`
- [ ] `macro_daily`
- [ ] `tase_trading_calendar`
- [ ] `features_daily` (hypertable)
- [ ] `features_at_event` **with `market_cap_bucket` + `liquidity_bucket` columns** ← **קריטי**
- [ ] `ingestion_runs`
- [ ] `data_corrections_log`
- [ ] `dropped_events_log`
- [ ] `quarantine_log`
- [ ] `reconciliation_results`
- [ ] `decisions_log` ← **חדש ב-V1.0.1**
- [ ] `model_deployments` ← **חדש ב-V1.0.1**
- [ ] `paper_trading_results` ← **חדש ב-V1.0.1**

### SQL Functions
- [ ] `prices_daily_as_of(p_as_of TIMESTAMPTZ)`
- [ ] `events_as_of(p_window_start, p_window_end, p_as_of)`
- [ ] `features_at_event_as_of(p_event_ids, p_feature_set_version, p_as_of)`
- [ ] `companies_as_of(p_as_of)`
- [ ] `macro_daily_as_of(p_as_of)`
- [ ] `intraday_quotes_summary_as_of(p_as_of)` ← **חדש ב-V1.0.1**
- [ ] `is_trading_day(p_date DATE)`
- [ ] `subtract_trading_days(p_end_date, p_n_trading_days)` ← **חדש ב-V1.0.1**
- [ ] `add_trading_days(p_start_date, p_n_trading_days)` ← **חדש ב-V1.0.1**

### Indices (sample of must-haves)
- [ ] `idx_feat_event_buckets ON features_at_event(market_cap_bucket, liquidity_bucket)` ← **חדש**
- [ ] `idx_events_company_obs ON events(company_id, event_observable_at) WHERE superseded_at IS NULL AND is_quarantined = FALSE`
- [ ] `idx_prices_active ON prices_daily(company_id, business_date) WHERE superseded_at IS NULL`
- [ ] `idx_intraday_summary_active` ← **חדש**

### Triggers
- [ ] Block UPDATE on raw_* tables
- [ ] Block DELETE on raw_* tables (except by retention job with explicit role)
- [ ] Validate `decisions_log.decision IN ('take','skip')`
- [ ] Validate `paper_trading_results.user_confirmed = TRUE` (per Contract §7.8)

---

## 4. CI / Smoke Test Requirements

חובה לעבור לפני כל merge ל-main. Failure = block.

### 4.1 Schema integrity tests

```sql
-- TEST: insert without buckets must fail
INSERT INTO features_at_event (event_id, feature_set_version, features, company_id, event_observable_at)
VALUES (gen_random_uuid(), 'v1.0', '{}', gen_random_uuid(), now());
-- Expected: ERROR (NOT NULL violation on market_cap_bucket)

-- TEST: invalid bucket value must fail
INSERT INTO features_at_event (..., market_cap_bucket, liquidity_bucket)
VALUES (..., 'huge', 'mid');
-- Expected: ERROR (CHECK constraint)
```

### 4.2 Target formula consistency test

```python
def test_target_formula_consistency():
    """
    Target computation in Decision Model must match Contract §5.4 exactly.
    Tests against fixed snapshot (input → expected output).
    """
    snapshot = [
        # (forward_return_5d, spread_pct, expected_label)
        (0.020, 0.002,  1),  # return > (0.0030 + 0.004) * 1.5 = 0.0105 ✓
        (0.005, 0.002,  0),  # return < 0.0105 ✗
        (0.015, 0.005,  1),  # return > (0.0030 + 0.010) * 1.5 = 0.0195 ✗ → 0
        (0.025, 0.005,  1),  # return > 0.0195 ✓
    ]
    for ret, spread, expected in snapshot:
        actual = compute_target(forward_return=ret, spread_pct=spread)
        assert actual == expected, f"Formula drift: ret={ret}, spread={spread}"
```

(Re-verify expected values manually against current Contract — last test case may need adjustment. Test catches drift, calibrate baseline once.)

### 4.3 Embargo uses trading calendar test

```python
def test_embargo_is_trading_days():
    """
    Embargo must consult tase_trading_calendar, not calendar arithmetic.
    """
    # Pick a Friday in training data
    friday = date(2024, 1, 5)  # Friday in TASE calendar
    
    # subtract 5 trading days from following Monday
    monday = date(2024, 1, 8)
    result = subtract_trading_days(monday, 5)
    
    # If implementation uses calendar days, result = 2024-01-03 (Wednesday)
    # If implementation uses trading days, result = 2023-12-28 (5 trading days back)
    
    assert result == date(2023, 12, 28), \
        f"Embargo not using trading calendar: got {result}"

def test_no_calendar_day_embargo():
    """
    Static check: 'timedelta(days=5)' next to 'embargo' must not appear in code.
    """
    forbidden_pattern = re.compile(r'timedelta\(days=\d+\)\s*#?\s*embargo', re.I)
    for py_file in glob('src/**/*.py'):
        content = open(py_file).read()
        assert not forbidden_pattern.search(content), \
            f"FORBIDDEN: calendar-day embargo in {py_file}"
```

### 4.4 decisions_log accepts only valid decisions

```sql
-- TEST: invalid decision must fail
INSERT INTO decisions_log (event_id, decision, reason, p_point, p_lower_p10, p_upper_p90, threshold_applied, model_version, feature_set_version)
VALUES (gen_random_uuid(), 'maybe', 'unsure', 0.55, 0.45, 0.65, 0.55, 'v1.0', 'v1.0');
-- Expected: ERROR (CHECK constraint)

-- TEST: CI ordering must be valid
INSERT INTO decisions_log (..., p_point, p_lower_p10, p_upper_p90, ...)
VALUES (..., 0.5, 0.7, 0.3, ...);  -- p10 > p_point or p_point > p90
-- Expected: ERROR (CHECK constraint)
```

### 4.5 Raw UPDATE/DELETE must fail

```sql
-- TEST: UPDATE on raw must fail
UPDATE raw_price_snapshots SET close = 999 WHERE ingestion_id = 1;
-- Expected: ERROR (trigger blocks UPDATE)

-- TEST: DELETE on raw must fail
DELETE FROM raw_filings WHERE ingestion_id = 1;
-- Expected: ERROR (trigger blocks DELETE)
```

### 4.6 No same-day price reference test

```python
def test_no_same_day_close_in_features():
    """
    Static check: no SQL pattern that joins prices on event date.
    """
    forbidden = re.compile(
        r'business_date\s*=\s*DATE\s*\(\s*event_observable_at\s*\)',
        re.I
    )
    for sql_file in glob('src/**/*.sql') + glob('src/**/*.py'):
        content = open(sql_file).read()
        assert not forbidden.search(content), \
            f"FORBIDDEN: same-day price reference in {sql_file}"
```

### 4.7 Random label test (Decision Model only)

```python
def test_random_label_no_edge():
    """
    Train on shuffled labels. AUC on validation must be ~0.50.
    Per Decision Model §9.1.
    """
    y_random = np.random.RandomState(42).permutation(y_train.values)
    model = train_primary(X_train, y_random, w_train, C=1.0)
    auc = roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])
    assert 0.45 <= auc <= 0.55, f"LEAKAGE: random labels achieve AUC={auc}"
```

### 4.8 As-of bypass detection (lint)

```python
# In CI: scan for direct queries on bitemporal tables
def test_no_bitemporal_bypass():
    forbidden_tables = ['prices_daily', 'events', 'companies', 'features_at_event',
                        'macro_daily', 'corporate_actions', 'intraday_quotes_summary']
    
    # Pattern: any FROM clause referencing these tables in non-migration code
    for py_file in glob('src/**/*.py'):
        if '/migrations/' in py_file:
            continue
        content = open(py_file).read()
        for table in forbidden_tables:
            # Allow only via _as_of() function calls
            direct_pattern = re.compile(
                rf'\bFROM\s+{table}\b(?!\s*_as_of)',
                re.I | re.MULTILINE
            )
            assert not direct_pattern.search(content), \
                f"FORBIDDEN: direct query on {table} in {py_file}; use {table}_as_of()"
```

### 4.9 Reproducibility test

```python
def test_training_is_deterministic():
    """
    Same input + same C → same coefficients (within float precision).
    """
    model_a = train_primary(X_train, y_train, w_train, C=1.0)
    model_b = train_primary(X_train, y_train, w_train, C=1.0)
    assert np.allclose(model_a.coef_, model_b.coef_, atol=1e-10)
```

---

## 5. Definition of Done — Phase 1

Phase 1 = Schema + Ingestion infrastructure (Data Layer Roadmap weeks 1-4).

**לא מסיימים Phase 1 עד שכל הסעיפים בuhecklist הזה passed:**

### 5.1 Migrations
- [ ] All migrations in `src/migrations/` reviewed (PR with 1+ approver, but for solo: self-review with 24h gap).
- [ ] `alembic upgrade head` runs cleanly on **fresh DB** (no errors, no warnings).
- [ ] `alembic downgrade base` runs cleanly (full rollback works end-to-end).
- [ ] `alembic upgrade head` runs cleanly **after** downgrade (idempotent migrations).
- [ ] All 25+ tables from §3 above exist with correct schema (`\d table_name` matches spec).
- [ ] All 9 SQL functions from §3 exist and are callable.

### 5.2 Smoke Tests Pass
- [ ] §4.1 (schema integrity): all assertions pass.
- [ ] §4.4 (decisions_log validation): pass.
- [ ] §4.5 (raw immutability): pass.
- [ ] §4.6 (no same-day close): static check passes on empty codebase.
- [ ] §4.8 (no as-of bypass): static check passes on empty codebase.
- [ ] CI runs all of the above in < 5 minutes total.

### 5.3 Rollback Tested
- [ ] On staging environment: `alembic downgrade -1` after a successful upgrade rolls back the most recent migration.
- [ ] No data loss in `raw_*` tables during downgrade (those tables are NEVER dropped automatically).
- [ ] `pg_dump` of staging executed and stored to backup location.
- [ ] `pg_restore` from that backup verified on a separate empty database.
- [ ] **Recovery time documented:** record actual RTO achieved.

### 5.4 Seed Data Loaded
- [ ] `tase_trading_calendar`: minimum 5 years backward + 1 year forward populated.
- [ ] `companies`: at least all current TA-35 + TA-90 members (~125 companies) loaded.
- [ ] `index_membership_history`: TA-35 + TA-90 history ≥ 5 years backward.
- [ ] `macro_daily`: VIX, SP500, USDILS, BOI_RATE for last 5 years.
- [ ] At least 1 month of `prices_daily` for TA-35 universe loaded for verification.
- [ ] Verification query: `SELECT COUNT(*) FROM prices_daily_as_of(now()) WHERE business_date = (last trading day)` returns expected count.

### 5.5 No Forbidden Patterns in CI
- [ ] CI lint job for `timedelta(days=N).*embargo` passes (zero matches).
- [ ] CI lint job for `business_date = DATE(event_observable_at)` passes (zero matches).
- [ ] CI lint job for direct queries on bitemporal tables passes.
- [ ] CI runs on every PR, blocks merge on failure.

### 5.6 Documentation Locks
- [ ] All four V1.0.1 docs committed under `docs/spec/`.
- [ ] Git tag `v1.0.1-spec` created at the commit.
- [ ] Git branch protection on `main`: requires CI green + 1 approver (self-approve OK for solo).
- [ ] `README.md` at repo root with:
  - Project mission (1-2 sentences).
  - Link to all four V1.0.1 docs.
  - Compliance disclaimer (Contract §7.10).
  - Quick start: `make migrate && make smoke-test`.

### 5.7 Sign-off

```
Phase 1 complete:    ____________________   Date: __________
Reviewer (self):     Same                    Date: __________
Next phase:          Phase 2 — Ingestion (TASE EOD prices, MAYA scraper)
```

---

## 6. Common Pitfalls — Don't

מהשטח. ראיתי את אלה כשלים שוב ושוב ב-projects דומים:

1. **"זה רק בdev, אני אסדר אחר כך."**
   `WHERE business_date = DATE(event_observable_at)` "כדי להאיץ" → נשכח → backtest מציג AUC=0.78 → live שלילי.

2. **"ה-embargo של calendar days קרוב מספיק."**
   3 trading days במקום 5. ב-50 events = ~5% מהtrain set מציצים לעתיד.

3. **"ה-bucket אני מחשב ב-Python at query time."**
   Inconsistent computations between feature_builder ו-Memory query. עדיף DB column מוגדר.

4. **"`UPDATE prices_daily SET adj_close = ...` כי המקור תיקן."**
   זה לא תיקון, זה זיוף היסטורי. INSERT new record + supersede.

5. **"אני קורא ישר מ-events כי `events_as_of()` איטי."**
   Index חסר על events או pool גדול. תקן את ה-index, אל תעקוף.

6. **"אני מוסיף עמודה ל-raw כי קל יותר."**
   Raw immutable. הוסף ל-staging או curated.

7. **"ה-test הזה נכשל כי ההגדרה לא מדויקת. אני מסמן xfail."**
   אם test נכשל → או הקוד שגוי או ה-spec שגוי. לא mark xfail. תפתור.

8. **"LightGBM נותן AUC טוב יותר. אני אעביר אותו ל-primary."**
   Contract §7.x. שינוי architecture = V2 amendment. לא code change.

---

## 7. When to Stop and Re-Read Spec

תפסיק לכתוב קוד ותחזור ל-spec docs במצבים האלה:

- צריך להוסיף עמודה ל-table.
- צריך לשנות ערך של hyperparameter.
- בודק "האם מותר להשתמש בfeature X."
- מרגיש שאתה מתחיל לעקוף משהו.
- code reviewer (אפילו עצמך after 24h) שאל "למה?".
- test נכשל ואתה רוצה לשנות assertion.
- מאריך window כדי לקבל יותר דאטה.
- שוקל "רק לבדוק" model אחר.

ב-MVP, **discipline > velocity**. ספרינט מהיר עם bug latent = חודש איבוד מאוחר יותר.

---

## 8. Quick Reference Card

מספרים שיהיו מול עיניך:

| מטרה | ערך |
|---|---|
| Holding horizon | 5 trading days |
| Cost margin | × 1.5 |
| Cost base (round-trip) | 0.0030 + 2 × spread_pct |
| Decision threshold | 0.55 |
| Decision threshold (Memory insufficient) | 0.65 |
| Auto-skip if CI crosses | 0.5 |
| Embargo | 5 trading days |
| Recency half-life | 3 years |
| History window | 15 years |
| k for k-NN | 50 |
| Min pool stage 1 | 50 |
| Min ESS | 20 |
| Bootstrap models | 100 |
| Tier weights | {1.0, 0.8, 0.5, 0.2} |
| Min training samples | 300 |
| Sharpe soft kill | < 0.3 |
| Drawdown soft kill | > 15% |
| Hit rate floor | 50% |
| Promotion Sharpe | ≥ 0.6 |

| Bucket | market_cap_log | liquidity_score |
|---|---|---|
| large | ≥ 9.5 | ≥ 0.7 |
| mid | 8.5–9.5 | 0.4–0.7 |
| small | < 8.5 | < 0.4 |

---

**END OF IMPLEMENTATION GUARDRAILS V1.0.1**
