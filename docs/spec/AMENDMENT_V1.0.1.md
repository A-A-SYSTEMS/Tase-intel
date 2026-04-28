# AMENDMENT V1.0.1 — Cross-Document Consistency Fixes

> **Effective:** ____________
> **Triggers re-validation:** ❌ NO (no validation has run yet — pre-implementation)
> **Affects documents:**
> - `TECHNICAL_CONTRACT_V1.md` → V1.0.1
> - `DATA_LAYER_SPEC_V1.md` → V1.0.1
> - `DECISION_MODEL_SPEC_V1.md` → V1.0.1

---

## 0. Authority

תיקון זה מבוצע על בסיס `V1_CROSS_DOCUMENT_REVIEW.md` (decision: APPROVED WITH FIXES). התיקון מטפל ב-3 ממצאי HIGH ו-4 ממצאי MEDIUM שמצריכים תיקון לפני implementation. ממצאי LOW (L1-L6) נדחים ל-amendment עתידי או נכללים אגב הדרך.

**תיקון זה מתבצע לפני שריצה של אימון או backtest כלשהי החלה.** לכן אין צורך ב-restart של validation framework — אין מה לעשות restart לו. לאחר ה-amendment הזה, V1.0.1 הוא ה-baseline שעליו validation תרוץ לראשונה.

---

## 1. Summary of Changes

| ID | Severity | Change |
|---|---|---|
| H1 | 🔴 HIGH | Target formula אוחדה ל: `target = 1 if forward_return_5d > total_costs × 1.5`; הוסר `transaction_costs = 0.0015` המוטעה. |
| H2 | 🔴 HIGH | `market_cap_bucket` ו-`liquidity_bucket` הוספו ל-`features_at_event` schema + feature_builder logic. |
| H3 | 🔴 HIGH | Embargo עכשיו מחושב ב-trading days דרך `tase_trading_calendar`, לא calendar days. |
| M1 | 🟡 MEDIUM | Naming אוחד: feature נקרא `event_source_tier`, column נקראת `source_tier`, יחס ביניהם מוגדר במפורש. |
| M2 | 🟡 MEDIUM | תועדו required keys ב-`features_at_event.features` JSONB, כולל auxiliary fields. |
| M3 | 🟡 MEDIUM | הוספו ל-Data Layer: `decisions_log`, `model_deployments`, `paper_trading_results`. |
| M4 | 🟡 MEDIUM | Schema של `intraday_quotes_summary` הוגדר; missing-spread fallback ל-ADV-only מתועד מפורשות. |

תיקונים שכן בוצעו אגב הדרך מתוך LOW:
- L1: הברה של embargo placement (train→val + val→test) ב-Contract.
- L2: tagger_confidence pre-check הוסף ל-Decision Model decision flow.
- L3: as-of helper functions תועדו ב-Data Layer §5.4.

תיקונים שלא בוצעו (נדחים):
- L4 (claimed_at term): cosmetic; לא חוסם implementation.
- L5 (p10 vs p_lower_p10): cosmetic; לא חוסם implementation.
- L6 (paper_trading_log): subsumed by M3 fix.

---

## 2. Detailed Changes

### Change H1 — Target Formula Unification

**Before (Contract §5.4):**
> Binary: `1` אם `forward_return_5d > transaction_costs + spread × 2`, אחרת `0`.
> `transaction_costs = 0.0015` (15 bps round-trip, ראה 8.4).

**After (Contract §5.4 + Decision Model §3.1, identical):**
> Binary: `target = 1 if forward_return_5d > total_costs × 1.5 else 0`
>
> ```
> total_costs = commission_round_trip + slippage_round_trip + (spread_pct × 2)
>             = 0.0020 + 0.0010 + (spread_pct × 2)
>             = 0.0030 + (spread_pct × 2)
> ```
>
> כאשר `spread_pct` הוא ה-bid-ask spread של המניה ב-t-1 (היום שלפני `event_observable_at`), נלקח מ-`features_at_event.features.spread_pct`.

**Justification:** הנוסחה ב-§5.4 הקודמת לא הייתה מסונכרנת עם §8.4 של אותו מסמך. הנוסחה החדשה תואמת ל-§8.4 ול-Decision Model — total ≥ 0.0030 round-trip, plus spread, plus 1.5× safety margin.

**Impact:**
- שיעור ה-`take` labels בdata יורד (סף קשוח יותר).
- אין impact על training (לא רץ עדיין).

### Change H2 — Bucket Fields Added to features_at_event

**Before (Data Layer §4.4):**
```sql
CREATE TABLE features_at_event (
    event_id UUID PRIMARY KEY REFERENCES events(event_id),
    feature_set_version TEXT NOT NULL,
    features JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    company_id UUID NOT NULL,
    event_observable_at TIMESTAMPTZ NOT NULL
);
```

**After (Data Layer §4.4):**
```sql
CREATE TABLE features_at_event (
    event_id UUID PRIMARY KEY REFERENCES events(event_id),
    feature_set_version TEXT NOT NULL,
    features JSONB NOT NULL,
    -- Bucketed dimensions for Memory hard filtering (Contract §4.1)
    market_cap_bucket TEXT NOT NULL,    -- 'large' | 'mid' | 'small'
    liquidity_bucket TEXT NOT NULL,     -- 'large' | 'mid' | 'small'
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    company_id UUID NOT NULL,
    event_observable_at TIMESTAMPTZ NOT NULL,
    CHECK (market_cap_bucket IN ('large', 'mid', 'small')),
    CHECK (liquidity_bucket IN ('large', 'mid', 'small'))
);

CREATE INDEX idx_feat_event_buckets ON features_at_event(market_cap_bucket, liquidity_bucket);
```

Bucket computation in feature_builder:

```python
def compute_market_cap_bucket(market_cap_log: float) -> str:
    if market_cap_log >= 9.5:
        return 'large'
    elif market_cap_log >= 8.5:
        return 'mid'
    else:
        return 'small'

def compute_liquidity_bucket(liquidity_score: float) -> str:
    if liquidity_score >= 0.7:
        return 'large'
    elif liquidity_score >= 0.4:
        return 'mid'
    else:
        return 'small'
```

ערכי ה-thresholds זהים ל-Contract §4.1 ומוקפאים.

### Change H3 — Embargo Now in Trading Days

**Before (Decision Model §5.1):**
```python
val_end = test_start - timedelta(days=5)  # embargo
train_end = val_start - timedelta(days=5)  # embargo
```

**After (Decision Model §4.3 + §5.1):**
```python
def subtract_trading_days(end_date: date, n_trading_days: int) -> date:
    """
    Returns the date that is n_trading_days strictly before end_date,
    using the TASE trading calendar.
    """
    cursor = end_date
    days_subtracted = 0
    while days_subtracted < n_trading_days:
        cursor -= timedelta(days=1)
        if is_trading_day(cursor):  # consults tase_trading_calendar
            days_subtracted += 1
    return cursor

# In refit_decision_model():
val_end = subtract_trading_days(test_start, 5)
train_end = subtract_trading_days(val_start, 5)
```

`is_trading_day()` reads from `tase_trading_calendar` (Data Layer §3.6).

Contract §8.1 updated to clarify embargo applies in **two** places: train→val AND val→test (Finding L1 also resolved):

```
Train window: 5 שנים
[5 trading days embargo]
Validation window: 1 שנה
[5 trading days embargo]
Test window: 1 שנה
Refit cadence: כל 6 חודשים
```

### Change M1 — Source Tier Naming Unified

**Resolution:** the **column** in DB is `source_tier`. The **feature** in the model input vector is `event_source_tier`. The mapping is documented:

- Contract §3.4 amended: "מקור דאטה: `events.source_tier` (computed at ingestion via fixed lookup table from `events.source_type`)."
- Data Layer §4.3 (events table) amended: comment on `source_tier` column added: "1..4 (Contract §3.4); derived from `source_type` via fixed lookup; renamed to `event_source_tier` in feature vector."
- Decision Model §2.1 unchanged (still `event_source_tier`).

### Change M2 — features_at_event.features Required Keys Documented

**Added to Data Layer §4.4:**

```sql
features JSONB NOT NULL,
-- REQUIRED KEYS (validated at write time):
--
-- Model features (Contract §3, used by Decision Model):
--   event_type_l1            : str
--   event_type_l2            : str | null
--   event_magnitude          : float
--   event_source_tier        : int (1..4)
--   market_cap_log           : float
--   sector                   : str
--   liquidity_score          : float (0..1)
--   vix_level                : float
--   ta35_trend               : float
--   usdils_5d_change         : float
--   recent_return_20d        : float
--   volatility_20d           : float
--
-- Missing flags:
--   event_magnitude_missing  : 0 | 1
--
-- Auxiliary fields (NOT model features; required for cost calc / target / Memory):
--   spread_pct               : float (used in cost model and target)
--   market_cap_ils           : numeric (raw market cap)
--   adv_20                   : numeric (20-day average daily volume in ILS)
--
-- All values must be non-null for required keys (NaN → drop event upstream).
```

A Pydantic schema enforces this at write time:

```python
class FeaturesPayload(BaseModel):
    # Model features
    event_type_l1: str
    event_type_l2: Optional[str]
    event_magnitude: float
    event_source_tier: int = Field(ge=1, le=4)
    market_cap_log: float
    sector: str
    liquidity_score: float = Field(ge=0, le=1)
    vix_level: float
    ta35_trend: float
    usdils_5d_change: float
    recent_return_20d: float
    volatility_20d: float
    
    # Missing flags
    event_magnitude_missing: int = Field(ge=0, le=1)
    
    # Auxiliary
    spread_pct: float = Field(ge=0)
    market_cap_ils: Decimal = Field(gt=0)
    adv_20: Decimal = Field(ge=0)
```

### Change M3 — Decision Layer Tables Added to Data Layer

הוסף section חדש ב-Data Layer §4.6 בשם "Decision Layer Tables". מכיל:
- `decisions_log` (כפי שהוגדר ב-Decision Model §8.4).
- `model_deployments`.
- `paper_trading_results`.

ראה גרסה מתוקנת של Data Layer לDDL מלא.

### Change M4 — intraday_quotes_summary Schema + Fallback Policy

**Schema added to Data Layer §4.3:**

```sql
CREATE TABLE intraday_quotes_summary (
    company_id UUID NOT NULL REFERENCES companies(company_id),
    business_date DATE NOT NULL,
    avg_bid_ask_spread NUMERIC,           -- absolute spread, ILS
    avg_spread_pct NUMERIC,                -- spread / mid_price
    avg_mid_price NUMERIC,
    primary_source TEXT,                   -- 'tase_intraday' | 'computed_from_ticks' | ...
    sample_count INT,                      -- # observations aggregated
    is_synthetic BOOLEAN DEFAULT FALSE,    -- TRUE if fallback (sector median used)
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (company_id, business_date, recorded_at)
);

CREATE INDEX idx_intraday_summary_active ON intraday_quotes_summary(company_id, business_date)
    WHERE superseded_at IS NULL;
```

**Fallback policy explicitly stated in Data Layer §3.1 + Contract §3.7:**

> ב-MVP, אם spread data מ-TASE intraday אינו זמין:
> 1. **Tier 1 fallback:** sector median spread של 60 הימים האחרונים, marked `is_synthetic = TRUE`.
> 2. **Tier 2 fallback:** אם אין מספיק data לחשב sector median → spread = 0.005 (50 bps), conservative default, marked `is_synthetic = TRUE`.
> 3. כל event שcomputed עם synthetic spread מקבל flag ב-features_at_event.features.spread_is_synthetic = 1.
> 4. ב-V2 משוקלים על קניית data מקור intraday מובנה.

---

## 3. Versioning

לאחר amendment זה:

| Document | Version | Date |
|---|---|---|
| TECHNICAL_CONTRACT_V1.0.1.md | V1.0.1 | ____________ |
| DATA_LAYER_SPEC_V1.0.1.md | V1.0.1 | ____________ |
| DECISION_MODEL_SPEC_V1.0.1.md | V1.0.1 | ____________ |
| AMENDMENT_V1.0.1.md | (this doc) | ____________ |
| V1_CROSS_DOCUMENT_REVIEW.md | V1.0 | (unchanged, historical) |

המסמכים הישנים (V1.0) נשמרים בריפו תחת tag `v1.0-spec` ל-historical reference. כל reference חדשה תכוון ל-V1.0.1.

---

## 4. Risk Assessment of Amendment

| Risk | Mitigation |
|---|---|
| New target formula different from V1.0 | אין impact — לא רץ training עדיין. |
| Bucket computation introduces bug | bucket logic deterministic, לא תלוי tuning; thresholds פרוזנים. |
| Trading-day embargo more restrictive | טוב — מחמיר על leakage prevention. |
| New tables in Data Layer | additive, לא breaking. |
| Source tier naming clarification | cosmetic, אין impact runtime. |

**סיכון כולל: נמוך.** אף שינוי לא breaks any existing code (אין code עדיין). אבל המסמכים אחרי amendment הם מסונכרנים, וזה מונע bugs בעתיד.

---

## 5. Sign-Off

```
Amended by:     Claude (Anthropic, drafting)
Approved by:    ____________________   Date: __________
Effective:      Upon owner signature
Status:         Pending owner sign-off
```

---

**END OF AMENDMENT V1.0.1**
