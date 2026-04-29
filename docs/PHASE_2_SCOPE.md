# Phase 2 Scope — tase-intel

> **Phase:** Phase 2 — Data Ingestion & Entity Resolution
> **Spec baseline:** V1.0.1
> **Author:** Netanel Luzon
> **Created:** 2026-04-29
> **Status:** DRAFT — pending owner approval
> **Prerequisite:** Phase 1 sign-off (tag `v1.0.1-phase1-complete`, commit `21c4c0e`)

---

## 1. Mission

Phase 2 populates the tables that Phase 1 built but left empty. Its single
objective is to deliver **reliable, reproducible, anti-leakage-compliant data
ingestion** for all four source families required by the V1.0.1 spec: TASE
prices, regulatory filings, news headlines, and macro indicators.

At the end of Phase 2, the system will have:

- A populated `companies` table covering all active and recently-delisted TA-35
  and TA-90 members, with entity resolution infrastructure.
- Daily EOD prices in `prices_daily` with at least 5 years of history, sourced
  from TASE Data Hub (primary) and EODHD (fallback), with cross-source
  reconciliation.
- Raw regulatory filings in `raw_filings` from MAYA (primary) and MAGNA
  (secondary). Raw ingestion only — parsing is Phase 3.
- Raw news headlines in `raw_news` from Israeli financial RSS feeds.
- Macro daily series (VIX, SP500, USD/ILS, BoI rate) in `raw_macro` and
  curated in `macro_daily`.
- Israeli holiday overlay on `tase_trading_calendar`, correcting the Phase 1
  limitation (Section 6.2 of Phase 1 Sign-off).
- `index_membership_history` for TA-35 and TA-90 with at least 5 years of
  history.
- Ingestion run logging in `ingestion_runs` for every job.
- Cross-source price reconciliation producing `reconciliation_results`.

Phase 2 does **not** produce events, features, models, or decisions. Those are
Phase 3+.

---

## 2. What Phase 2 Includes

1. **TASE EOD price ingestion** — daily pipeline from TASE Data Hub API into
   `raw_price_snapshots` and curated into `prices_daily` via
   `staging_prices_normalized`. Includes corporate actions awareness for
   `adj_close` validation.

2. **EODHD fallback ingestion** — secondary price source for cross-validation
   and gap-filling. Activated automatically when TASE primary is unavailable.

3. **Entity resolution v1** — populating `companies`, `company_tickers_history`,
   and `company_aliases` for the TA-35 + TA-90 universe. Deterministic
   resolution cascade (ISIN → ticker → normalized name) per Data Layer Spec
   Section 6.

4. **MAYA scraper** — polling MAYA archive for regulatory filings, storing raw
   HTML/PDF metadata in `raw_filings` and document blobs on local filesystem.
   Raw ingestion only — no parsing in Phase 2.

5. **MAGNA scraper** — polling MAGNA archive (ISA) for regulatory filings,
   storing raw metadata in `raw_filings` with `source = 'magna'`. MAGNA is
   secondary to MAYA; only filings not already captured via MAYA are ingested.
   Raw ingestion only — no parsing in Phase 2.

6. **News RSS poller** — polling Globes, TheMarker, Calcalist, Bizportal, and
   Ynet Economy RSS feeds into `raw_news`. Headline-hash tracking for
   retroactive edit detection.

7. **Macro ingestion** — FRED API for VIX and SP500; Bank of Israel API for
   USD/ILS and BoI rate. Raw into `raw_macro`, curated into `macro_daily`.

8. **Israeli holiday calendar overlay** — `seed_holidays.py` script that marks
   known Israeli holidays as `is_trading_day = FALSE` in
   `tase_trading_calendar`, addressing Phase 1 limitation Section 6.2.

9. **Index membership history** — populating `index_membership_history` with
    TA-35 and TA-90 composition changes for the past 5+ years.

10. **Cross-source reconciliation** — daily job comparing prices across TASE
    and EODHD, logging results in `reconciliation_results` per Data Layer Spec
    Section 9.3.

11. **Ingestion logging** — every job records a run in `ingestion_runs` with
    status, record counts, and error summaries per Data Layer Spec Section 4.5.

12. **Smoke tests for ingestion** — tests verifying idempotency, raw
    immutability compliance, and basic data quality of ingested records.

---

## 3. What Phase 2 Excludes

The following are explicitly **out of scope** for Phase 2. Attempting any of
these before Phase 2 sign-off violates the batch discipline.

| Item | Deferred to | Rationale |
|------|-------------|-----------|
| Event tagging (NLP pipeline) | Phase 3 | Requires populated filings + news + entity resolution stable |
| Feature computation (`features_daily`, `features_at_event`) | Phase 3+ | Requires events + prices + macro all populated |
| Decision Model training | Phase 4 | Requires features computed |
| Market Memory layer | Phase 5 | Requires features + events + historical depth |
| Paper trading | After Phase 5 | Requires full pipeline end-to-end |
| Live trading | After 12mo paper | Contract Section 7.9 — non-negotiable |
| Filing parsing (`staging_filings_parsed`) | Phase 3 | Requires entity resolution stable + tagger design |
| Intraday quotes ingestion | Phase 2b or 3 | Spread data from TASE paid tier; synthetic fallback sufficient for now |
| Smart Money / institutional data | V2 | Contract Section 7.6 — not in MVP |
| Streaming infrastructure (Kafka) | V2 | Data Layer Section 7.6 — batch is sufficient for MVP |
| Grafana dashboard | Phase 2b | Nice-to-have; manual SQL queries suffice initially |
| Prefect orchestration | Phase 2b | Manual/cron scheduling first; Prefect when job count warrants it |

---

## 4. Ingestion Principles

These principles govern all ingestion code written in Phase 2. They derive
directly from the V1.0.1 spec documents and are non-negotiable.

### 4.1 Raw is immutable

All source data lands first in `raw_*` tables. These tables have:
- `INSERT` only — `UPDATE` and `DELETE` blocked by triggers (Phase 1).
- `UNIQUE` constraints enabling idempotent re-ingestion via
  `ON CONFLICT DO NOTHING`.
- Full source payloads preserved in `raw_payload JSONB`.

**Reference:** Data Layer Spec Section 0 ("Raw is bronze — nothing deleted,
nothing updated"), Section 4.1, Implementation Guardrails Section 2.3.

### 4.2 Idempotency

Every ingestion job must be safe to run multiple times. Mechanisms:
- Raw: `UNIQUE(source, ..., payload_hash)` — duplicate = no-op.
- Curated: bitemporal write only if values actually changed.
- Calendar/seed: `ON CONFLICT DO UPDATE` (established in Phase 1).

Running a job twice must produce the identical final state as running it once.
This is enforced by tests in every ingestion batch.

**Reference:** Data Layer Spec Section 7.2.

### 4.3 Lineage

Every curated record must trace back to its raw source. The
`ingestion_lineage JSONB` column in `prices_daily` records which
`raw_price_snapshots.ingestion_id` produced it. Every staging record
references its parent raw `ingestion_id`.

No curated record may exist without a traceable path to a raw record. If the
raw record is missing or corrupt, the curated record is not written.

**Reference:** Data Layer Spec Section 1.1, Section 4.5.

### 4.4 Anti-leakage timestamps

- `fetched_at` (our clock, UTC) is the ground truth for when data became
  available to us, not the source's claimed timestamp.
- `event_observable_at` will be computed in Phase 3, but the raw timestamps
  that feed it (`fetched_at`, `filing_published_at`, `publisher_claimed_at`)
  must be captured accurately now.
- All timestamps stored as `TIMESTAMPTZ` in UTC. No bare `TIMESTAMP` columns.

**Reference:** Data Layer Spec Section 8.2, Implementation Guardrails
Section 2.6.

### 4.5 Retries and error handling

Network failures use exponential backoff (1s, 5s, 30s, 5m, 30m; max 5
attempts). Auth failures (401/403) alert immediately, no retry. Schema/parse
failures quarantine, no retry. Empty responses retry once after 30 minutes.

All failures are logged in `ingestion_runs` with `status = 'failed'` or
`status = 'partial'` and an `error_summary`.

**Reference:** Data Layer Spec Section 7.3.

### 4.6 Source priority

For prices: TASE Data Hub > EODHD > Yahoo Finance (cross-validation only).
For filings: MAYA > MAGNA (MAGNA is complement; only filings not already
captured via MAYA are ingested from MAGNA).
Reconciliation mismatches resolved per Data Layer Spec Section 9.3 severity
tiers.

**Reference:** Data Layer Spec Section 3.1, Section 3.2-3.3.

### 4.7 No schema changes without amendment

Phase 2 ingestion code must work with the existing V1.0.1 schema. If any
ingestion requirement discovers a missing column or constraint, it requires a
spec amendment before implementation. The schema is the spec's territory.

**Reference:** Technical Contract Section 10, Data Layer Spec Section 0.

### 4.8 Pydantic validation at system boundary

Every record entering the database passes through a Pydantic model that
validates types, ranges, and required fields before insertion. Invalid records
are quarantined, not silently dropped. The raw record itself is still saved
(raw is immutable evidence), but downstream processing is blocked.

**Reference:** Data Layer Spec Section 9.1.

### 4.9 Bitemporal writes for curated tables

Curated tables (`prices_daily`, `companies`, `macro_daily`, etc.) use
bitemporal columns (`recorded_at`, `superseded_at`). Updates are never
in-place: the old record is superseded (`superseded_at = now()`) and a new
record is inserted. This preserves full history of what was known when.

**Reference:** Data Layer Spec Section 5.

### 4.10 Hash-based deduplication

Every raw payload is hashed (SHA-256). The `payload_hash` column, combined
with source and date in `UNIQUE` constraints, prevents duplicate ingestion of
identical data. Re-fetching the same data from the same source on the same
date is a no-op if the payload hash matches. If the hash differs (source
correction), a new raw record is created, preserving both versions.

**Reference:** Data Layer Spec Section 4.1, Implementation Guardrails
Section 2.8.

---

## 5. Data Sources — Detailed

### 5.1 TASE Prices & Indices (Tier 1)

| Attribute | Value |
|-----------|-------|
| Source | TASE Data Hub API (`data.tase.co.il`) |
| Method | REST API, authenticated |
| Schedule | Daily 19:00 IST (primary) + 22:00 IST (adjustment re-fetch) |
| Raw table | `raw_price_snapshots` |
| Staging table | `staging_prices_normalized` |
| Curated table | `prices_daily` |
| Critical fields | `business_date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `shares_outstanding` |
| Backfill | 5 years minimum (2021-01-01 to present) |
| Fallback | EODHD API (`eodhd.com`) |
| Cost | ~500-2,000 NIS/month (TASE); $20-50/month (EODHD) |

**Ingestion flow:**
```
TASE API response
    -> Pydantic validation (RawPricePayload)
    -> INSERT INTO raw_price_snapshots (ON CONFLICT DO NOTHING)
    -> Normalize to staging_prices_normalized
    -> Promote to prices_daily (bitemporal insert)
    -> Log in ingestion_runs
```

**Backfill strategy:** Historical data fetched in date-range batches (1 month
per request). Rate limiting respected. Progress tracked via `ingestion_runs`.

### 5.2 EODHD Fallback Prices

| Attribute | Value |
|-----------|-------|
| Source | EODHD API (`eodhd.com`) |
| Method | REST API |
| Schedule | Daily 23:00 IST (cross-validation); on-demand when TASE unavailable |
| Purpose | Gap-fill + reconciliation |

EODHD records enter the same `raw_price_snapshots` table with
`source = 'eodhd'`. The staging normalizer resolves conflicts per source
priority (TASE > EODHD).

### 5.3 MAYA Filings (Tier 1)

| Attribute | Value |
|-----------|-------|
| Source | MAYA archive (`mayafiles.tase.co.il`) |
| Method | Web scraping (no public API) |
| Schedule | Every 30 min during 09:00-17:30 IST (trading days); every 2h otherwise |
| Raw table | `raw_filings` |
| Blob storage | Local filesystem: `/data/raw/maya/{yyyy}/{mm}/{dd}/{filename}` |
| Critical fields | `source_doc_id`, `filing_published_at`, `document_url`, `document_hash` |

**Scraper resilience:** DOM changes are expected. The scraper must:
- Save raw listing HTML daily as evidence.
- Use resilient selectors (data attributes > CSS classes).
- Alert on structural changes (missing expected elements).
- Never crash on unexpected HTML — quarantine and continue.

**PDF handling:** PDFs are stored as blobs on local filesystem. Only metadata
and filesystem path enter the database. No parsing in Phase 2 — full text
extraction and filing classification are Phase 3.

### 5.4 MAGNA Filings (Tier 2)

| Attribute | Value |
|-----------|-------|
| Source | MAGNA archive (`magna.isa.gov.il`) |
| Method | Web scraping; partial XML endpoint available |
| Schedule | Every 2 hours, 24/7 |
| Raw table | `raw_filings` (with `source = 'magna'`) |
| Critical fields | `source_doc_id`, `filing_published_at`, `document_url`, `document_hash` |

MAGNA is secondary to MAYA. Most filings overlap (~80%). Only filings not
already present via MAYA are ingested from MAGNA. Reconciliation identifies
coverage gaps. Raw ingestion only — no parsing in Phase 2.

**Reference:** Data Layer Spec Section 3.3.

### 5.5 News RSS (Tier 1)

| Attribute | Value |
|-----------|-------|
| Sources | Globes, TheMarker, Calcalist, Bizportal, Ynet Economy |
| Method | RSS feed polling |
| Schedule | Every 15 minutes, 24/7 |
| Raw table | `raw_news` |
| Critical fields | `headline`, `summary`, `url`, `fetched_at`, `publisher_claimed_at` |

**Key rules:**
- `fetched_at` (our UTC timestamp) is the anti-leakage anchor, not
  `publisher_claimed_at`.
- Headlines are hashed. Same URL with different headline hash = retroactive
  edit; both records preserved (per Data Layer Spec Section 3.4).
- RSS feeds typically expose only the last ~50 items. Polling frequency of 15
  minutes ensures no items are missed.
- No full article scraping in Phase 2 (legal, per Data Layer Spec Section 3.4).

### 5.6 Macro & FX (Tier 1)

| Series | Source | Schedule | Raw field |
|--------|--------|----------|-----------|
| VIX (`VIXCLS`) | FRED API | Daily 23:00 IST | `raw_macro` |
| S&P 500 (`SP500`) | FRED API | Daily 23:00 IST | `raw_macro` |
| USD/ILS official | Bank of Israel API | Daily 18:30 IST | `raw_macro` |
| BoI interest rate | Bank of Israel API | Daily 18:30 IST | `raw_macro` |

**Time zone alignment:** NY close != TLV close. All timestamps stored in UTC.
VIX and SP500 values for a given date represent the NY close of that date.

**Forward-fill policy:** VIX from FRED sometimes arrives T+1. Forward-fill up
to 3 days per Technical Contract Section 6.3. USD/ILS forward-fill up to 2
days.

**Backfill:** 5+ years of daily history for all four series.

---

## 6. Batch Roadmap

Phase 2 is divided into confirmed batches (9-13) and tentative batches
(14-20). Each batch is small, gated, and must pass before the next begins.

### Confirmed Batches

| Batch | Name | Deliverable | Gate criteria |
|-------|------|-------------|---------------|
| 9 | Phase 2 scope document | This document (`PHASE_2_SCOPE.md`) | Owner review + approval |
| 10 | Holiday calendar overlay | `seed_holidays.py` + updated calendar smoke tests | All known Israeli holidays 2021-2027 marked; `is_trading_day` tests pass |
| 11 | Entity resolution + companies seed | `companies`, `company_aliases`, `company_tickers_history` populated for TA-35 + TA-90 | >= 120 active companies; ISIN-based resolution; smoke tests |
| 12 | TASE EOD price ingestion | `raw_price_snapshots` + `prices_daily` pipeline | 1 month of prices for full TA-35 ingested and verified; idempotent re-run |
| 13 | EODHD fallback + reconciliation | EODHD ingestion + `reconciliation_results` | Cross-source comparison for 1 month; mismatch rate documented |

### Tentative Batches

| Batch | Name | Deliverable | Notes |
|-------|------|-------------|-------|
| 14 | Historical price backfill | 5 years of `prices_daily` for full universe | Rate limiting; may take multiple runs |
| 15 | Macro ingestion (FRED + BoI) | `raw_macro` + `macro_daily` populated | 4 series, 5 years history |
| 16 | Index membership history | `index_membership_history` populated | TA-35 + TA-90 composition, 5 years |
| 17 | MAYA scraper | `raw_filings` populated with recent MAYA filings | Scraper robust to DOM changes; raw only, no parsing |
| 18 | MAGNA scraper | `raw_filings` populated with MAGNA filings | Secondary source; complement to MAYA |
| 19 | News RSS poller | `raw_news` populated from 5 RSS feeds | Headline-hash dedup; 15-min polling |
| 20 | Phase 2 sign-off | `PHASE_2_SIGNOFF.md`; all ingestion verified | Definition of Done checklist |

**Batch ordering rationale:**
- Holiday calendar (10) first because price ingestion depends on accurate
  trading days.
- Entity resolution (11) before prices (12) because `prices_daily` requires
  `company_id` foreign keys.
- TASE primary (12) before EODHD fallback (13) because reconciliation
  compares against primary.
- Prices before macro (15) because macro is simpler and can parallel.
- MAYA (17) before MAGNA (18) because MAGNA deduplicates against MAYA.
- MAYA/MAGNA and news (19) are independent of prices and can be reordered if
  needed.
- Tentative batches may be split, merged, or reordered based on API access
  timelines and discovery during implementation.

---

## 7. Definition of Done — Phase 2

Phase 2 is complete when all of the following are verified:

### 7.1 Companies & Entity Resolution

- [ ] `companies` table populated with >= 120 active TA-35 + TA-90 members.
- [ ] `companies` includes recently-delisted members (>= 5 years back).
- [ ] Every company has a valid `primary_isin`, `canonical_name_he`, `sector`.
- [ ] `company_aliases` populated with at least ticker + one name variant per
      company.
- [ ] Entity resolution cascade (ISIN -> ticker -> name) implemented and
      tested.
- [ ] Smoke test verifies no orphan `company_id` references.

### 7.2 Prices

- [ ] `prices_daily` contains >= 5 years of daily prices for the full TA-35 +
      TA-90 universe.
- [ ] Every active company has price coverage >= 99.5% of trading days (per
      Data Layer Spec Section 9.4 threshold).
- [ ] `adj_close` present for all records.
- [ ] `raw_price_snapshots` contains the raw source payloads.
- [ ] EODHD fallback tested: simulated TASE outage correctly falls back.
- [ ] Reconciliation run on >= 1 month shows < 2% cross-source mismatch rate.
- [ ] Re-running ingestion for the same date range produces no duplicates
      (idempotent).

### 7.3 Macro

- [ ] `macro_daily` contains VIX, SP500, USD/ILS, BoI rate for >= 5 years.
- [ ] Forward-fill gaps <= 3 days for VIX, <= 2 days for USD/ILS.
- [ ] `raw_macro` contains source payloads.
- [ ] Re-run safe (idempotent).

### 7.4 Filings

- [ ] MAYA scraper successfully polls and stores filings in `raw_filings`.
- [ ] MAGNA scraper successfully polls and stores filings in `raw_filings`.
- [ ] PDF blobs stored on filesystem with correct paths in DB.
- [ ] MAGNA filings deduplicated against MAYA (no duplicate `source_doc_id`
      cross-source).
- [ ] Scrapers handle DOM changes gracefully (quarantine, not crash).
- [ ] Raw ingestion only — no `staging_filings_parsed` writes in Phase 2.

### 7.5 News

- [ ] News RSS poller stores headlines from all 5 sources in `raw_news`.
- [ ] Retroactive headline edits detected via `headline_hash` and preserved as
      separate records.
- [ ] `fetched_at` accurately reflects our polling time, not publisher time.

### 7.6 Calendar

- [ ] Israeli holidays marked in `tase_trading_calendar` for 2021-2027.
- [ ] Holiday overlay is idempotent.
- [ ] Smoke tests verify specific known holidays (e.g., Yom Kippur, Pesach).

### 7.7 Index Membership

- [ ] `index_membership_history` populated for TA-35 and TA-90 with >= 5 years
      of composition changes.
- [ ] Bitemporal columns (`recorded_at`, `superseded_at`) correctly populated.

### 7.8 Infrastructure

- [ ] Every ingestion job logs to `ingestion_runs`.
- [ ] CI remains green throughout Phase 2 (no regressions).
- [ ] Forbidden-pattern lint still passes (no new violations).
- [ ] All new code covered by tests.

---

## 8. Risks

### 8.1 Bad data from sources

**Risk:** Sources may return corrupt, malformed, or nonsensical data (e.g.,
negative prices, zero volume on a trading day, impossible OHLC relationships
where high < low, garbled Hebrew text in filings).

**Mitigation:** Pydantic validation at ingestion boundary catches type and
range violations. Sanity checks (Data Layer Spec Section 9.2) flag anomalies
like daily price changes > 50% without corporate actions. Invalid records are
quarantined, not silently promoted to curated tables. Raw records are always
preserved regardless of validation outcome.

**Impact if unmitigated:** Corrupt data propagates to curated tables, poisons
features and backtests in Phase 3+.

### 8.2 Duplicate data

**Risk:** Re-running ingestion jobs, network retries, or overlapping poll
windows may attempt to insert the same record multiple times. Source APIs may
return overlapping date ranges during backfill.

**Mitigation:** All raw tables have `UNIQUE` constraints on
`(source, ..., payload_hash)` enabling `ON CONFLICT DO NOTHING`. Curated
tables use bitemporal writes that only insert if values actually changed.
Idempotency tests verify that running a job N times produces the same final
state as running it once.

**Impact if unmitigated:** Inflated row counts, incorrect aggregations,
double-counted volume, and misleading reconciliation results.

### 8.3 Missing dates (gaps in history)

**Risk:** Some trading days may have no price data for specific companies due
to source gaps, trading halts, or API pagination issues. Delisted companies
may have incomplete historical records.

**Mitigation:** Daily completeness checks (Data Layer Spec Section 9.4)
compare expected (company, date) pairs against actual records. Companies with
> 0.5% missing days per quarter are flagged. Known gaps are documented. Data
is never fabricated to fill gaps — missing is better than wrong.

**Impact if unmitigated:** Incomplete feature windows cause event drops in
Phase 3+. Survivorship bias if only well-covered companies survive.

### 8.4 Incorrect trading calendar

**Risk:** The Phase 1 calendar marks Sun-Thu as trading and Fri-Sat as
non-trading, but does not handle Israeli holidays. If holidays are not
overlaid before price ingestion, the system will expect prices on days the
exchange was closed, triggering false gap alerts.

**Mitigation:** Holiday calendar overlay (Batch 10) is sequenced before any
price ingestion (Batch 12). The overlay script covers all major Israeli
holidays (Yom Kippur, Pesach, Sukkot, Rosh Hashana, etc.) for 2021-2027.
Smoke tests verify specific known holiday dates.

**Impact if unmitigated:** False completeness gaps, incorrect embargo
calculations, wrong trading-day arithmetic in Phase 3+ features.

### 8.5 Provider API changes or discontinuation

**Risk:** Any external API (TASE Data Hub, EODHD, FRED, BoI, MAYA, MAGNA) may
change endpoints, authentication, response format, rate limits, or pricing
without notice. MAYA and MAGNA (web scraping) are especially fragile.

**Mitigation:** Scrapers use resilient selectors and save raw HTML as
evidence. API clients validate response schemas before processing. Structural
change detection alerts on unexpected formats. Quarantine unparseable
responses rather than crashing. Fallback sources exist for prices (EODHD) and
macro data (Yahoo Finance for VIX/SP500).

**Impact if unmitigated:** Ingestion pipelines break silently or noisily,
creating data gaps until manually fixed.

### 8.6 Survivorship bias in historical data

**Risk:** If only currently-listed companies are ingested, the historical
record excludes companies that were delisted, merged, or went bankrupt. This
creates survivorship bias — the illusion that all companies in the universe
performed well historically.

**Mitigation:** Both TASE Data Hub and EODHD provide delisted company data.
The `companies` table tracks `delisting_date`, `delisting_reason`, and
`delisting_successor_company_id`. Entity resolution covers all historical
TA-35/TA-90 members from 2010 onward (~150-200 entities including delisted).
A KPI tracks `% of historical index members that are delisted` — if < 15%,
data is considered incomplete.

**Reference:** Data Layer Spec Section 1.1, Section 6.7.

**Impact if unmitigated:** Backtests show unrealistically positive results.
Model trained on survivorship-biased data fails in production.

### 8.7 Look-ahead bias in timestamp handling

**Risk:** Using a source's claimed publication time (`publisher_claimed_at`,
`filing_published_at`) instead of our fetch time (`fetched_at`) as the moment
data became available. Headlines edited retroactively. VIX values from FRED
that arrive T+1 but are backdated to T+0.

**Mitigation:** `fetched_at` (our UTC clock) is always recorded and is the
ground truth for data availability. `publisher_claimed_at` is metadata only.
Headline edits are detected via `headline_hash` changes — both versions
preserved. Timezone alignment rules are documented and tested per source. All
timestamps are `TIMESTAMPTZ` in UTC per Implementation Guardrails Section 2.6.

**Reference:** Data Layer Spec Section 8.2, Section 8.3.

**Impact if unmitigated:** Subtle data leakage that inflates backtest
performance. Features appear to predict the future because they secretly use
future information.

### 8.8 TASE API access delay

**Risk:** TASE Data Hub API access requires a commercial agreement. Approval
may take weeks.

**Mitigation:** Begin with EODHD as temporary primary. EODHD covers TASE
securities including delisted. Once TASE API access is granted, switch primary
and reconcile historical data.

**Impact if unmitigated:** Batches 12-14 blocked until API access confirmed.

### 8.9 Entity resolution ambiguity

**Risk:** Israeli company names appear in Hebrew, English, abbreviated, and
variant forms across sources. Fuzzy matching may produce false positives.

**Mitigation:** Prioritize deterministic matching (ISIN, ticker) over fuzzy.
All fuzzy matches require manual review (`review_status = 'auto_suggested'`).
Build conservative: prefer false negatives (quarantine) over false positives
(wrong company).

**Impact if unmitigated:** Events mapped to wrong companies corrupt historical
data and downstream features.

### 8.10 Rate limiting and throttling

**Risk:** API providers (TASE, EODHD, FRED, BoI) may rate-limit requests,
especially during historical backfill.

**Mitigation:** Implement exponential backoff per Data Layer Spec Section 7.3.
Backfill in small batches with configurable delays. Track progress in
`ingestion_runs` for resumability.

**Impact if unmitigated:** Backfill takes longer than expected; potential
temporary bans.

### 8.11 RSS feed reliability

**Risk:** RSS feeds may change URL, format, or stop publishing without notice.
Some feeds expose only 20-50 recent items.

**Mitigation:** Multiple sources provide redundancy. 15-minute polling
frequency prevents missing items from short feeds. Monitor feed health via
`ingestion_runs` status tracking.

**Impact if unmitigated:** News coverage gaps for specific publishers.

### 8.12 Scope creep beyond raw ingestion

**Risk:** With filings and news ingested, temptation to start event tagging,
filing parsing, or feature computation ("just a quick prototype") before the
designated phase.

**Mitigation:** Phase 2 explicitly excludes event tagging, filing parsing,
and feature computation. No `staging_filings_parsed`, `events`, or
`features_daily` writes in Phase 2. The scope document (this document) and
batch gates enforce this boundary. Code review rejects any PR that writes to
Phase 3+ tables.

**Impact if unmitigated:** Premature, untested logic contaminating the
pipeline. Violation of batch discipline.

---

## 9. Hard Deferrals

These items are known requirements from the V1.0.1 spec that are explicitly
deferred past Phase 2. They are documented here to prevent scope creep and
ensure nothing is forgotten.

| # | Item | Spec reference | Deferred to |
|---|------|---------------|-------------|
| 1 | Event tagging (L1/L2 classification) | Technical Contract Section 3.1-3.2 | Phase 3 |
| 2 | Filing parsing (`staging_filings_parsed`) | Data Layer Section 4.2 | Phase 3 |
| 3 | Feature computation pipeline | Technical Contract Section 3, Data Layer Section 4.4 | Phase 3+ |
| 4 | Decision Model (LightGBM / Logistic Regression) | Technical Contract Section 5, Decision Model Spec | Phase 4 |
| 5 | Market Memory retrieval layer | Technical Contract Section 4 | Phase 5 |
| 6 | Paper trading infrastructure | Technical Contract Section 7.9 | After Phase 5 |
| 7 | Intraday quotes (real spread data) | Data Layer Section 4.3 | Phase 2b or 3 |
| 8 | Prefect orchestration | Data Layer Section 2 (tech stack) | Phase 2b |
| 9 | Grafana monitoring dashboard | Data Layer Section 9.7 | Phase 2b |
| 10 | Backup procedure + recovery drill | Data Layer Section 10.7-10.8 | Phase 2b |
| 11 | Streaming infrastructure | Data Layer Section 7.6 | V2 |
| 12 | Smart Money / institutional data | Technical Contract Section 7.6 | V2 |

**Phase 2b** refers to optional infrastructure improvements that may be done
between Phase 2 sign-off and Phase 3 start, if time permits. They are not
gating for Phase 3.

---

## 10. Approval

By signing below, the owner certifies:

- [ ] The Phase 2 scope described in Section 2 is correct and complete.
- [ ] The exclusions in Section 3 are understood and accepted.
- [ ] The ingestion principles in Section 4 align with V1.0.1 spec.
- [ ] The batch roadmap in Section 6 is a reasonable ordering.
- [ ] The risks in Section 8 are acknowledged with acceptable mitigations.
- [ ] The hard deferrals in Section 9 are understood and will not be attempted
      in Phase 2.
- [ ] Phase 1 sign-off (`PHASE_1_SIGNOFF.md`) is prerequisite and verified.

### Discipline carry-forward

The same discipline from Phase 1 continues:

- Spec docs are the source of truth. Changes require amendments.
- Each batch is small, gated, and reviewed before the next begins.
- CI must remain green throughout. A red `main` branch blocks progress.
- Forbidden-pattern lint continues to run. New ingestion code must not
  introduce forbidden patterns.
- No schema changes without spec amendment.
- Raw tables remain immutable. Ingestion code uses `INSERT` only.

### Signature

```
Owner:            ____________________   Date: __________
Status:           DRAFT  ->  ____________
Phase 2 batches may begin: yes / no
```

---

**END OF PHASE 2 SCOPE**
