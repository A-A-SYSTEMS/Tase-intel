# V1 CROSS-DOCUMENT CONSISTENCY REVIEW

> **Reviewer:** Claude (Anthropic)
> **Review Date:** ____________
> **Documents Reviewed:**
> - `TECHNICAL_CONTRACT_V1.md` (V1.0)
> - `DATA_LAYER_SPEC_V1.md` (V1.0)
> - `DECISION_MODEL_SPEC_V1.md` (V1.0)
>
> **Methodology:** Targeted text search + schema cross-reference + parameter consistency check.
> Focus on contradictions, undefined references, leakage risks, and implementation gaps.

---

## Executive Summary

**Decision: APPROVED WITH FIXES**

נמצאו **13 ממצאים**: 3 ב-severity HIGH, 4 ב-severity MEDIUM, 6 ב-severity LOW. שלושת ממצאי ה-HIGH **חייבים להיות מתוקנים לפני implementation** — אחד מהם הוא inconsistency בין Contract ל-Decision Model בנוגע ל-target formula, שאם לא יתוקן ייצור labels שגויים בdata.

ארבעת ממצאי ה-MEDIUM הם פערים שיגרמו לבלבול במהלך implementation אם לא יתוקנו, אך לא יגרמו ל-correctness bugs.

ממצאי ה-LOW הם cosmetic/documentation polish.

לאחר ביצוע התיקונים המסומנים `MUST FIX` ו-`SHOULD FIX`, הסט מוכן ל-V1.0.1.

---

## Findings — High Severity (MUST FIX)

### Finding H1: Target Formula Inconsistency (Contract vs Decision Model)

**Severity:** 🔴 HIGH — Affects training labels directly. Will produce fundamentally different model behavior.

**Description:** המסמכים מגדירים שתי נוסחאות שונות לחישוב ה-target:

**Contract §5.4:**
```
target = 1 if forward_return_5d > transaction_costs + spread × 2 else 0
transaction_costs = 0.0015 (15 bps round-trip)
```
→ Threshold = `0.0015 + spread × 2` ≈ `0.0015 + 0.005 = ~0.0065` (lenient)

**Decision Model §3.1:**
```
total_costs = commission_round_trip + spread_at_event * 2 + slippage_assumption
            = 0.0020 + (spread_pct * 2) + 0.0010
            = 0.0030 + spread component
target = 1 if forward_return_5d > total_costs * 1.5 else 0
```
→ Threshold = `(0.0030 + spread × 2) × 1.5` ≈ `0.0045 + spread × 3 = ~0.010` (strict)

**הבעיה:** Decision Model's threshold הוא בערך פי שניים יותר מחמיר מ-Contract's. זה ישפיע ישירות על:
- שיעור ה-`take` labels בdata (target rate).
- ה-precision/recall של המודל.
- הbacktest performance.

**Recommended Fix:**

תיקון Contract §5.4 כדי שיתאים ל-Validation §8.4 ול-Decision Model:

```
target = 1 if forward_return_5d > total_costs × 1.5 else 0

total_costs = commission_round_trip + slippage_round_trip + (spread_pct × 2)
            = 0.0020 + 0.0010 + (spread_pct × 2)
            = 0.0030 + (spread_pct × 2)
```

הסר את השורה `transaction_costs = 0.0015 (15 bps round-trip, ראה 8.4)` — היא שגויה ולא מסונכרנת עם 8.4.

**Action:** Bump Contract V1.0 → V1.0.1. Update §5.4. Re-sign Contract.

---

### Finding H2: `market_cap_bucket` and `liquidity_bucket` Undefined in Data Layer

**Severity:** 🔴 HIGH — Memory layer cannot be implemented as specified.

**Description:** Contract §4.1 (Memory Pool Definition) משתמש ב-hard filters:
```
H.market_cap_bucket == Q.market_cap_bucket  (3 buckets)
H.liquidity_bucket == Q.liquidity_bucket    (3 buckets)
```

Contract §4.1 גם מגדיר את ה-bucketing thresholds (Large/Mid/Small).

אבל Data Layer Spec **לא** מגדיר:
- Field `market_cap_bucket` בשום טבלה (לא ב-`features_at_event`, לא ב-`companies`, לא במקום אחר).
- Field `liquidity_bucket` בשום טבלה.
- Procedure לחישוב buckets מ-`market_cap_log` ו-`liquidity_score`.

**הבעיה:** המפתח שמיישם Memory query יצטרך להחליט עצמאית:
1. אם לחשב buckets on-the-fly בכל query (slow).
2. אם להוסיף עמודות ל-`features_at_event`.
3. אם לאחסן ב-bitemporal table נפרדת.

ההחלטה הזו צריכה להיות מתוקנת ב-spec, לא בזמן ריצה.

**Recommended Fix:**

הוסף ל-Data Layer §4.4 (`features_at_event` schema):

```sql
-- Add to features_at_event:
ALTER TABLE features_at_event 
    ADD COLUMN market_cap_bucket TEXT,    -- 'large' | 'mid' | 'small'
    ADD COLUMN liquidity_bucket TEXT;     -- 'large' | 'mid' | 'small'

CREATE INDEX idx_feat_event_buckets ON features_at_event(
    market_cap_bucket, liquidity_bucket
);
```

ועדכן את ה-feature_builder pipeline להעלות את ה-buckets בעת חישוב ה-features (לפי thresholds מ-Contract §4.1).

**Action:** Bump Data Layer V1.0 → V1.0.1. Update §4.4. Update feature_builder process.

---

### Finding H3: Embargo Unit Inconsistency (Trading Days vs Calendar Days)

**Severity:** 🔴 HIGH — Potential leakage in walk-forward validation.

**Description:**

**Contract §8.1:** "Embargo: 5 ימי מסחר בין train ל-test"  
**Decision Model §4.1:** "Embargo: 5 trading days between train end & test start"

אבל ה-implementation ב-Decision Model §5.1:
```python
val_end = test_start - timedelta(days=5)  # embargo
train_end = val_start - timedelta(days=5)  # embargo
```

`timedelta(days=5)` הוא **5 ימים קלנדריים, לא 5 ימי מסחר**. אם train_end חל ביום חמישי, val_start יהיה ביום שלישי הבא — רק 3 ימי מסחר embargo במקום 5.

(וב-§4.3 יש ניסיון לתיקון עם `embargo_days * 1.5` שזה approximation לא מדויקת.)

**הבעיה:** ב-real walk-forward, חלק מה-refits יקבלו embargo של 3-4 ימי מסחר במקום 5. זה לא מספיק כדי להגן מפני אירוע שהשפעתו 5 ימים, ויוצר leakage potential.

**Recommended Fix:**

החלף את החישוב בDecision Model §5.1:

```python
from datetime import date, timedelta

def subtract_trading_days(end_date: date, n_trading_days: int) -> date:
    """Get the date that is n_trading_days BEFORE end_date in the TASE calendar."""
    cursor = end_date
    days_subtracted = 0
    while days_subtracted < n_trading_days:
        cursor -= timedelta(days=1)
        if is_trading_day(cursor):  # consults tase_trading_calendar
            days_subtracted += 1
    return cursor

# Replace in refit_decision_model():
val_end = subtract_trading_days(test_start, 5)
train_end = subtract_trading_days(val_start, 5)
```

`is_trading_day()` קורא מ-`tase_trading_calendar` (Data Layer §3.6).

**Action:** Bump Decision Model V1.0 → V1.0.1. Update §4.3 + §5.1. Add explicit dependency on `tase_trading_calendar`.

---

## Findings — Medium Severity (SHOULD FIX)

### Finding M1: `source_tier` Naming Inconsistency

**Severity:** 🟡 MEDIUM — Cosmetic but causes implementation friction.

**Description:**
- Contract §3.4: feature נקרא `event_source_tier`.
- Contract §3.4 also says "מקור דאטה: `events.source_type` + lookup table."
- Data Layer §4.3 (events schema): column is `source_tier INT NOT NULL`.
- Decision Model §2.1: input feature `event_source_tier`.

שלוש שמות שונות לאותו דבר (`event_source_tier` / `source_type` / `source_tier`) + הCnotract טועה במקור (אומר `events.source_type` אבל ה-tier הוא ב-`events.source_tier`; `source_type` הוא 'filing'/'news'/'macro_derived').

**Recommended Fix:**

תקן את Contract §3.4:
```diff
- **מקור דאטה:** `events.source_type` + lookup table.
+ **מקור דאטה:** `events.source_tier` (computed at ingestion via lookup על `events.source_type`).
```

הוסף ל-Data Layer §4.3 כתגובה לעמודה:
```sql
source_tier INT NOT NULL,            -- 1..4 (Contract §3.4); derived from source_type via fixed lookup
```

**Action:** Bump Contract + Data Layer to V1.0.1.

---

### Finding M2: `spread_at_event` Not Explicitly Specified in `features_at_event` Schema

**Severity:** 🟡 MEDIUM — Implementation gap.

**Description:** Decision Model §3.7 (cost model) מתבסס על:
> `spread` נלקח מ-`features_at_event` (mean 20-day daily avg spread של המניה ב-t-1).

אבל Data Layer §4.4 (`features_at_event` schema) רק מציין `features JSONB`. לא מציין שה-JSONB חייב לכלול `spread_pct` field.

בנוסף, `spread` משמש ל-cost calculation ב-target generation, אבל הוא **לא** אחד מ-12 הfeatures של ה-model (Contract §3 לא כולל אותו).

**הבעיה:** developer יכול לשכוח להוסיף `spread_pct` ל-features payload, ובזמן training הtarget לא יחושב נכון.

**Recommended Fix:**

הוסף ל-Data Layer §4.4 docstring of `features_at_event.features`:

```sql
features JSONB NOT NULL,
-- Required keys:
--   12 model features (Contract §3): event_type_l1, event_type_l2, event_magnitude,
--     event_source_tier, market_cap_log, sector, liquidity_score, vix_level,
--     ta35_trend, usdils_5d_change, recent_return_20d, volatility_20d
--   Missing flags: event_magnitude_missing
--   Auxiliary fields (NOT model features, used for cost calc/target):
--     spread_pct, market_cap_ils, adv_20
```

**Action:** Bump Data Layer V1.0 → V1.0.1.

---

### Finding M3: `decisions_log` and `model_deployments` Tables Defined in Decision Model but Not in Data Layer

**Severity:** 🟡 MEDIUM — Schema spread across docs is OK, but ownership unclear.

**Description:** Decision Model §8.4 מגדיר schema של `decisions_log`. Decision Model §14.2 מתייחס ל-`model_deployments` שלא מוגדר באף מסמך.

Data Layer §4 (Database Schema) מגדיר 22 טבלאות אבל **לא** את `decisions_log` או `model_deployments`.

**הבעיה:** מי הוא ה-source of truth ל-schema של טבלאות ה-Decision Model? אם Data Layer הוא ה-spec הקאנוני של DB, אז `decisions_log` חייב להיות בו (גם אם הוא "owned" by Decision Model layer).

**Recommended Fix (option A — preferred):**

הוסף section ל-Data Layer §4.6 בשם "Decision Layer Tables":

```sql
-- ============================================================
-- decisions_log (owned by Decision Model layer)
-- ============================================================
CREATE TABLE decisions_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(event_id),
    decision TEXT NOT NULL,                    -- 'take' | 'skip'
    reason TEXT NOT NULL,
    p_point NUMERIC NOT NULL,
    p_lower_p10 NUMERIC NOT NULL,
    p_upper_p90 NUMERIC NOT NULL,
    threshold_applied NUMERIC NOT NULL,
    memory_flags TEXT[],
    model_version TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_decisions_event ON decisions_log(event_id);
CREATE INDEX idx_decisions_time ON decisions_log(decided_at DESC);

-- ============================================================
-- model_deployments
-- ============================================================
CREATE TABLE model_deployments (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL,
    deployed_by TEXT NOT NULL,
    deployment_metadata JSONB,
    superseded_at TIMESTAMPTZ,
    rollback_reason TEXT
);

-- ============================================================
-- paper_trading_results
-- ============================================================
CREATE TABLE paper_trading_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES decisions_log(decision_id),
    entry_date DATE NOT NULL,
    entry_price NUMERIC NOT NULL,
    exit_date DATE,
    exit_price NUMERIC,
    raw_return NUMERIC,
    net_return_after_costs NUMERIC,
    holding_days INT,
    closed_reason TEXT,                  -- 'horizon_reached' | 'manual_exit' | 'soft_kill'
    user_confirmed BOOLEAN NOT NULL,     -- per Contract 7.8
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Action:** Bump Data Layer V1.0 → V1.0.1. Add new section. Decision Model spec keeps its schema definition but adds reference to Data Layer.

---

### Finding M4: `intraday_quotes` Table Mentioned but Not Defined

**Severity:** 🟡 MEDIUM — Source of spread data is ambiguous.

**Description:** Contract §3.7 (liquidity_score):
> "מקור דאטה: `prices_daily` (volume, close), `intraday_quotes` (spread)."

Data Layer §3.1 מזכיר את הספק:
> "ספרד נתונים (bid-ask) לא תמיד זמין מ-TASE EOD. מקור נפרד: TASE intraday quotes (paid tier) או חישוב מ-tick data."

אבל **אין schema** ל-`intraday_quotes` table ב-Data Layer §4.

**הבעיה:** המפתח לא יודע איך לאחסן spread data. JSONB ב-prices_daily? Table נפרדת? View?

**Recommended Fix:**

הוסף ל-Data Layer §4.3:

```sql
-- ============================================================
-- intraday_quotes_summary (daily aggregate)
-- ============================================================
-- Daily aggregate of intraday spread data.
-- Tick-level data NOT stored (too large; aggregated at ingestion).
CREATE TABLE intraday_quotes_summary (
    company_id UUID NOT NULL REFERENCES companies(company_id),
    business_date DATE NOT NULL,
    avg_bid_ask_spread NUMERIC,           -- absolute spread
    avg_spread_pct NUMERIC,                -- spread / mid_price
    avg_mid_price NUMERIC,
    primary_source TEXT,
    sample_count INT,                      -- # ticks aggregated
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (company_id, business_date, recorded_at)
);

CREATE INDEX idx_intraday_summary_active ON intraday_quotes_summary(company_id, business_date)
    WHERE superseded_at IS NULL;
```

ועדכן Contract §3.7:
```diff
- **מקור דאטה:** `prices_daily` (volume, close), `intraday_quotes` (spread).
+ **מקור דאטה:** `prices_daily` (volume, close), `intraday_quotes_summary` (spread).
```

**Action:** Bump Contract + Data Layer to V1.0.1.

---

## Findings — Low Severity (NICE TO FIX)

### Finding L1: Embargo Placement (Train→Val Embargo Not in Contract)

**Severity:** 🟢 LOW — Decision Model implementation more conservative than Contract specifies.

**Description:**
- Contract §8.1: "Embargo: 5 ימי מסחר בין train ל-test."
- Decision Model §5.1 implements embargo train→val AND val→test.

Decision Model הוא יותר שמרני (טוב), אבל לא תואם ל-Contract literal text.

**Recommended Fix:** עדכן Contract §8.1:
```
Train window: 5 שנים
Validation window: 1 שנה (consecutive after train + 5 trading day embargo)
Test window: 1 שנה (consecutive after validation + 5 trading day embargo)
Refit cadence: כל 6 חודשים
```

**Action:** Bump Contract V1.0 → V1.0.1. Minor clarification.

---

### Finding L2: Tagger Confidence Filter Not Explicit in Decision Model

**Severity:** 🟢 LOW — Implicit assumption, should be explicit.

**Description:** Contract §6.6 קובע:
> "ב-MVP: אירועים עם tagger confidence < 0.6 לא מייצרים החלטות, רק נרשמים לreview ידני."

Decision Model §8.1 (`make_decision`) לא בודק `tagger_confidence`. כנראה ההנחה היא ש-events כאלה מוסננים לפני, אבל זה לא מצוין.

**Recommended Fix:** הוסף Rule 0 ב-Decision Model §8.1:
```python
def make_decision(p_point, p_lower_p10, p_upper_p90, memory_output, features, event):
    # Rule 0: Tagger confidence pre-check (per Contract 6.6)
    if event.tagger_confidence < 0.6:
        return 'skip', 'low_tagger_confidence'
    
    # Rule 1: Risk Pre-filter
    if features['liquidity_score'] < 0.4:
        ...
```

**Action:** Bump Decision Model V1.0 → V1.0.1.

---

### Finding L3: As-Of Helper Functions Partially Specified

**Severity:** 🟢 LOW — Documentation gap.

**Description:** Data Layer §5.4 מספק דוגמה ל-`prices_daily_as_of()` ואז אומר "Similar wrappers for events, companies, etc."

Decision Model §5.1 משתמש ב:
- `fetch_events_as_of(start, end, as_of=refit_date)`
- `build_features_targets(events)`

אלה לא מוגדרים ב-spec.

**Recommended Fix:** הוסף ל-Data Layer §5.4:

```sql
-- events_as_of: get all valid events up to as_of timestamp
CREATE OR REPLACE FUNCTION events_as_of(
    p_window_start TIMESTAMPTZ,
    p_window_end TIMESTAMPTZ,
    p_as_of TIMESTAMPTZ
)
RETURNS SETOF events AS $$
    SELECT DISTINCT ON (event_id) *
    FROM events
    WHERE event_observable_at >= p_window_start
      AND event_observable_at <= p_window_end
      AND recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
      AND is_quarantined = FALSE
    ORDER BY event_id, recorded_at DESC;
$$ LANGUAGE SQL STABLE;

-- features_at_event_as_of: similar
-- companies_as_of: similar
```

**Action:** Bump Data Layer V1.0 → V1.0.1.

---

### Finding L4: Term Inconsistency — `claimed_at` vs `event_timestamp` vs `publisher_claimed_at`

**Severity:** 🟢 LOW — Glossary cleanup needed.

**Description:**
- Contract Glossary: term is `claimed_at`.
- Data Layer schema: column for events is `event_timestamp`. For news raw is `publisher_claimed_at`. For filings raw is `filing_published_at`.

שלושה שמות בשימוש לאותו concept (timestamp שהמקור טוען עליו).

**Recommended Fix:** השאר את שמות העמודות ב-DB (יהיה harder לשנות retroactively), אבל עדכן את Contract Glossary:

```
| **claimed_at** | timestamp שהמקור טוען עליו (`event_timestamp` ב-events table, 
                   `publisher_claimed_at` ב-raw_news, `filing_published_at_tase` ב-raw_filings).
                   נרשם לcomparison אך לא משמש להחלטות |
```

**Action:** Bump Contract V1.0 → V1.0.1.

---

### Finding L5: Variable Naming `p_lower_p10` vs `p10`

**Severity:** 🟢 LOW — Cosmetic.

**Description:** Decision Model §7.2 משתמש ב-`p_lower_p10` ו-`p_upper_p90` כשמות. אבל בשאר ה-doc ובContract הם נקראים `p10`/`p90`.

**Recommended Fix:** Standardize ל-`p10` ו-`p90` בכל המסמכים.

**Action:** Bump Decision Model V1.0 → V1.0.1.

---

### Finding L6: `paper_trading_log` Table Referenced But Not Defined

**Severity:** 🟢 LOW — Subsumed by Finding M3.

**Description:** Contract §2 architecture diagram מציג "Paper Trading Log" אבל אין schema.

**Recommended Fix:** מטופל כחלק מ-Finding M3 ע"י הוספת `paper_trading_results` ל-Data Layer.

---

## Cross-Cutting Verification

### Q1: האם כל השמות עקביים?

| Term | Status |
|---|---|
| `event_observable_at` | ✓ Consistent across all 3 docs |
| `event_timestamp` | ✓ Used only in events schema; aligned with Contract glossary `claimed_at` (but see L4) |
| `company_id` | ✓ Consistent across all 3 docs |
| `features_at_event` | ✓ Consistent reference |
| `liquidity_score` | ✓ Consistent (0-1 range, 0.4 threshold) |
| `event_source_tier` | ⚠️ See M1 — column called `source_tier`, feature called `event_source_tier` |
| `tagger_version`, `parser_version` | ✓ Consistent |

### Q2: האם כל הפרמטרים עקביים?

| Parameter | Contract | Data Layer | Decision Model | Status |
|---|---|---|---|---|
| Recency half-life | 3 שנים | — | 3.0 years | ✓ |
| `liquidity_score < 0.4` (pre-filter) | ✓ | ✓ | ✓ | ✓ |
| Decision threshold = 0.55 | ✓ | n/a | ✓ | ✓ |
| Hardened threshold = 0.65 | ✓ | n/a | ✓ | ✓ |
| CI crossing 0.5 → skip | ✓ | n/a | ✓ | ✓ |
| Embargo = 5 trading days | ✓ | n/a | ⚠️ Calendar days in code | ❌ See H3 |
| Train window | 5 years | n/a | 5 years | ✓ |
| Validation window | 1 year | n/a | 1 year | ✓ |
| Test window | 1 year | n/a | 1 year | ✓ |
| Refit cadence | 6 months | n/a | 6 months | ✓ |
| Transaction costs (commission) | 0.20% RT | n/a | 0.20% RT | ✓ |
| Transaction costs (slippage) | 0.10% RT | n/a | 0.10% RT | ✓ |
| **Target formula** | `> costs + spread×2` (with costs=0.0015) | n/a | `> costs × 1.5` (with costs=0.0030+spread×2) | ❌ See H1 |
| Sharpe soft kill | < 0.3 | n/a | < 0.3 | ✓ |
| Drawdown soft kill | > 15% | n/a | > 15% | ✓ |
| Hit rate floor | 50% | n/a | 50% | ✓ |
| Min training samples | 300 | n/a | 300 | ✓ |
| `k` for k-NN | 50 | n/a | n/a | ✓ |
| Minimum pool stage 1 | 50 | n/a | n/a | ✓ |
| Bootstrap models n | n/a | n/a | 100 | ✓ |
| Tier weights | {1.0, 0.8, 0.5, 0.2} | n/a | n/a | ✓ |

### Q3: סתירות בין מסמכים

נמצאו **3 סתירות** (H1, H2, H3). כולן מטופלות לעיל.

### Q4: Decision Model מניח שדה שלא מובטח ב-Data Layer

| Assumption | Provided? |
|---|---|
| `events_as_of()` function | ⚠️ Implied, not specified — see L3 |
| `features_at_event_as_of()` | ⚠️ Implied — see L3 |
| `is_trading_day()` lookup | ✓ Provided via `tase_trading_calendar` |
| `decisions_log` table | ❌ Not in Data Layer — see M3 |
| `model_deployments` table | ❌ Not in Data Layer — see M3 |
| `paper_trading_results` table | ❌ Not in any doc — see M3/L6 |
| `market_cap_bucket` field | ❌ Not in features_at_event — see H2 |
| `liquidity_bucket` field | ❌ Not in features_at_event — see H2 |
| `spread_pct` in features payload | ⚠️ Required but not documented — see M2 |

### Q5: Data Layer מאפשר פעולה ש-Contract אוסר

לא נמצא. Data Layer לא מאפשר:
- ❌ Auto-execution (per Contract 7.8) — Data Layer לא מתאר execution layer.
- ❌ External access (per Contract 7.10) — Data Layer לא מציין API חיצוני.
- ❌ LLM in decision path (per Contract 7.4) — אין יצירת decisions ב-Data Layer.
- ❌ Memory as feature (per Contract 7.3) — Data Layer features layer לא משתמש ב-Memory output.

✓ Data Layer respects all Contract constraints.

### Q6: Leakage Risks Despite Anti-Leakage Spec

**זוהו 4 סיכוני leakage שעלולים להופיע ב-implementation למרות שה-spec מנסה למנוע:**

**LR1 — Embargo unit confusion (covered by H3):**
שימוש ב-calendar days במקום trading days יכול לאפשר 3 ימי mascher embargo במקום 5 כש-train_end חל לפני סוף שבוע.

**LR2 — Same-day close usage:**
Data Layer §8.3 אוסר על שימוש ב-same-day close, אבל ה-implementation של ה-feature builder יכול בטעות לקרוא `prices_daily WHERE business_date = DATE(event_observable_at)`. זה מסומן ב-Forbidden Patterns (§8.6) **אבל אין enforcement אוטומטי**.

**Recommendation:** הוסף CI test:
```python
def test_no_same_day_price_in_features():
    # For each event, verify prices used in feature computation
    # have business_date < DATE(event_observable_at)
    ...
```

**LR3 — Bitemporal query bypass:**
Data Layer §5.4 מסבירה את ה-helper functions, אבל אם developer מבטח כותב SQL ידני שלא משתמש ב-helpers, leakage קל. Anti-leakage rule §8.6 אוסר את זה אבל **אין enforcement**.

**Recommendation:** הוסף DB-level audit: כל query על `prices_daily`, `events`, `companies` שלא עוברת דרך ה-`*_as_of()` functions תרשם ב-`raw_query_log` ותעבור review שבועי.

**LR4 — Test set pollution via memory queries:**
Memory queries יכולות בטעות להחזיר events מ-test window ב-training. Contract §4.1 אומר "H.event_observable_at < Q.event_observable_at" אבל זה לא מספיק — אם Q מ-train window אבל H מ-test window שמוקדם יותר ממנו (לא יכול לקרות), אבל אם Q מ-test window אז H יכול להגיע מ-train (legitimate).

ה-bug היותר עדין: backtest ש-replay של test events משתמש בMemory pool שכולל events ש-tagger אחר tagged עכשיו אבל לא היה זמין בעבר. זה leakage עקיף.

**Recommendation:** Memory queries during backtest חייבות להעביר `as_of=event_observable_at` ל-`events_as_of()`. אכוף this בכל קריאה ל-Memory.

---

## Pre-Repo Checklist

לפני הכנסת המסמכים לריפו:

### Critical (Must Complete)

- [ ] **Fix H1:** עדכון Contract §5.4 (target formula).
- [ ] **Fix H2:** הוספת `market_cap_bucket` + `liquidity_bucket` ל-Data Layer §4.4.
- [ ] **Fix H3:** עדכון Decision Model §4.3 + §5.1 לchamado של trading days.
- [ ] **Bump כל המסמכים ל-V1.0.1.**
- [ ] **כל מסמך נחתם** עם תאריך + hash + chr signature line.
- [ ] **`AMENDMENT_V1.0.1.md`** נכתב ומפרט את התיקונים.

### Important (Should Complete)

- [ ] **Fix M1:** תיקון `source_tier` naming.
- [ ] **Fix M2:** documentation של required keys ב-`features_at_event.features` JSONB.
- [ ] **Fix M3:** הוספת `decisions_log`, `model_deployments`, `paper_trading_results` ל-Data Layer §4.6.
- [ ] **Fix M4:** הוספת `intraday_quotes_summary` schema.

### Nice (Can Complete Later)

- [ ] Fix L1-L6 (cosmetic + documentation polish).
- [ ] הוספת CI tests ל-LR2 + LR3 + LR4 (recommended in Q6).

### Repo Setup

- [ ] **`README.md`** ברמת הריפו עם:
   - מטרת הפרויקט (קצר).
   - link לשלושת המסמכים.
   - **אזהרה ברורה:** "This is not investment advice. Do not deploy with real money. See Technical Contract 7.10."
- [ ] **Git tag:** `v1.0.1-spec` אחרי שכל ה-MUST FIX מתוקנים.
- [ ] **`.gitignore`:** לוודא שאין secrets, credentials, או data dumps.
- [ ] **License file:** ב-MVP, "All Rights Reserved" + private repo. אסור public.
- [ ] **Branch protection:** main branch protected. כל change ל-spec דורש PR.

### Documentation Completeness

- [ ] לכל מסמך, חתימה ב-section האחרון (Owner + Date + Hash).
- [ ] Cross-references נבדקות (Contract §X → Data Layer §Y).
- [ ] Glossary terms ב-Contract תואמים לטקסט בכל המסמכים.

### Operational Setup (לא חלק מ-spec, אבל לפני implementation)

- [ ] Backup procedure ל-spec docs עצמם (Git remote ל-2 services).
- [ ] **`AMENDMENT_TEMPLATE.md`** מוכן בריפו ל-amendments עתידיים.
- [ ] **`PRE_MORTEM_V1.md`** נכתב ונחתם — 10 דרכים שהפרויקט יכול להיכשל + תגובה (per recommended in Contract §10).

---

## Summary Table

| ID | Severity | Document | Issue | Fix Required |
|---|---|---|---|---|
| H1 | 🔴 HIGH | Contract / Decision | Target formula inconsistency | MUST FIX |
| H2 | 🔴 HIGH | Data Layer | `market_cap_bucket` / `liquidity_bucket` undefined | MUST FIX |
| H3 | 🔴 HIGH | Decision Model | Embargo uses calendar days, not trading days | MUST FIX |
| M1 | 🟡 MEDIUM | Contract / Data Layer | `source_tier` naming inconsistency | SHOULD FIX |
| M2 | 🟡 MEDIUM | Data Layer | `spread_pct` required key not documented | SHOULD FIX |
| M3 | 🟡 MEDIUM | Data Layer / Decision | `decisions_log` etc not in Data Layer | SHOULD FIX |
| M4 | 🟡 MEDIUM | Data Layer | `intraday_quotes` table not defined | SHOULD FIX |
| L1 | 🟢 LOW | Contract | Train→val embargo not in spec | NICE |
| L2 | 🟢 LOW | Decision Model | Tagger confidence filter not explicit | NICE |
| L3 | 🟢 LOW | Data Layer | As-of helper functions partial | NICE |
| L4 | 🟢 LOW | Contract | `claimed_at` term inconsistency | NICE |
| L5 | 🟢 LOW | Decision Model | `p_lower_p10` vs `p10` naming | NICE |
| L6 | 🟢 LOW | Data Layer | `paper_trading_log` undefined (subsumed by M3) | NICE |

---

## Final Decision

**Status: APPROVED WITH FIXES**

הסט הקאנוני של V1 מאושר עם הדרישה לתיקון 3 הממצאים HIGH לפני any implementation work. ארבעת ה-MEDIUM יושלמו בתוך אותו amendment cycle (V1.0.1) כדי למנוע פגישת תיקונים מרובה.

לאחר השלמת התיקונים:
- **גרסה חדשה:** V1.0.1 לכל שלושת המסמכים.
- **`AMENDMENT_V1.0.1.md`** מתעד את התיקונים.
- **Re-sign** של כל המסמכים.
- **Git tag** `v1.0.1-spec`.

ואז — **OK to implement.**

לוח זמנים מומלץ לתיקונים: **2-4 שעות עבודה** למפתח שמכיר את המסמכים. קצר משמעותית מהזמן שיילקח לתקן את אותן בעיות אחרי שכתבת alas 3,000 שורות קוד.

---

## Signatures

```
Reviewer:     Claude (Anthropic)         Date: __________
Owner Sign-off: ____________________     Date: __________
Decision:     APPROVED WITH FIXES
Repo location: V1_CROSS_DOCUMENT_REVIEW.md
```

---

**END OF CROSS-DOCUMENT REVIEW V1**
