# TECHNICAL CONTRACT V1.0.1 — AI Trading Intelligence System for TASE

> **Status:** ACTIVE — V1.0.1
> **Effective Date:** ____________
> **Owner:** ____________
> **Last Amended:** V1.0 → V1.0.1 (see `AMENDMENT_V1.0.1.md`)
> **Next Review:** 6 חודשים מתאריך תחילה (לפני re-fit הראשון של ה-Decision Model)

---

## 0. Document Status & Authority

מסמך זה מהווה את ה-**Technical Contract** המחייב של המערכת. הוא נכתב **לפני** כתיבת קוד מערכתי כדי לקבע את גבולות העיצוב הסטטיסטי, ולמנוע scope creep, overfitting, ו-drift לאורך הפרויקט.

**כללי שינוי המסמך:**

1. כל שינוי בפרק 3 (Feature Dictionary), פרק 4 (Memory Spec), או פרק 7 (Design Constraints) דורש:
   - bump לגרסת המסמך (V1.0 → V1.1 או V2.0).
   - מסמך justification נפרד (`AMENDMENT_<version>.md`) המתאר את הסיבה לשינוי.
   - **restart מלא של validation framework** — backtest שרץ עם פיצ'רים ישנים אינו תקף לקבלת החלטה על מעבר ל-live עם פיצ'רים חדשים.
   - תאריך החלת השינוי.

2. שינויים בפרקים 6 (Failure Handling), 8 (Validation), ו-9 (Failure Criteria) דורשים גרסה חדשה אך לא בהכרח restart של backtest, אלא אם הם משפיעים מהותית על מה שנמדד.

3. **אסור** לשנות את המסמך retroactively. המסמך הוא immutable כלפי העבר; שינוי = גרסה חדשה.

4. כל ריצת backtest חייבת לתעד את גרסת ה-Contract שהיא מתבססת עליה.

---

## 1. Mission & Scope

### 1.1 מה המערכת **כן**

מערכת **decision-support סטטיסטית** ל-event-driven trading בשוק ההון הישראלי (TASE), שמטרתה:

- לזהות אירועים תאגידיים ושוקיים בעלי השלכות מסחריות (filings, earnings, guidance, geopolitical).
- להציג למשתמש **התפלגויות תגובה היסטוריות** באירועים דומים.
- לספק **המלצת take/skip** מבוססת מודל סטטיסטי דטרמיניסטי, עם confidence interval.
- לתעד כל החלטה ל-replayability מלא.

### 1.2 מה המערכת **לא**

- אינה מבצעת execution אוטומטי.
- אינה מתפקדת כייעוץ השקעות (לא מספקת המלצות אישיות לאחרים).
- אינה משתמשת ב-LLM לצורך החלטות מסחר.
- אינה מתיימרת לחזות מחירים — היא מציגה הסתברויות מבוססות עבר.

### 1.3 Universe ראשוני

- **מניות:** TA-35 + TA-90 (~125 חברות פעילות + delisted בתקופת ההיסטוריה).
- **טווח החזקה:** 1-10 ימי מסחר (לא intraday).
- **תדירות החלטה:** EOD (end-of-day) בלבד ב-MVP.

### 1.4 שלב התפעול הנוכחי

- **MVP:** Paper trading בלבד.
- **Promotion criteria ל-live:** ראה פרק 9.

---

## 2. Architecture (Reference)

```
Raw Data Sources
    ↓
Ingestion Layer (raw_*, immutable)
    ↓
Parsing Layer (staging_*, versioned)
    ↓
Curated Layer (companies, events, prices_daily)
    ↓
    ┌───────────────────────────┐
    ↓                           ↓
Feature Builder            Market Memory
(features_daily)           (probabilistic retrieval)
    ↓                           ↓
Risk Pre-filter                 │
    ↓                           │
Decision Model (deterministic)  │
    ↓                           ↓
Output (take/skip + CI) ←── Memory Output (median/p10/p90/n)
    ↓                           ↓
        User Decision Layer
                ↓
        Paper Trading Log
```

**Hard separation:** Memory output אינו feature במודל ההחלטה. הוא presentation layer בלבד למשתמש. ראה פרק 7.4.

---

## 3. Feature Dictionary

ה-Vector מכיל **12 features**, מקובעים. הוספה, הורדה, או שינוי תחשיב = bump גרסת Contract.

**יחס דגימות-לפיצ'ר נדרש:** ≥ 25 (target).
**גודל training set מינימלי לפעולה:** 300 דגימות בכל refit.

### 3.1 `event_type_l1`

| | |
|---|---|
| **Type** | Categorical |
| **Cardinality** | 6 ערכים סגורים |
| **Encoding** | Target encoding, Bayesian smoothing, k=30 |

**תיאור עסקי:** הסיווג הרחב ביותר של אירוע. מבוסס enum סגור: `earnings`, `guidance`, `regulatory`, `contracts`, `geopolitical`, `management`.

**מקור דאטה:** `events.event_type` (טבלת curated). תיוג ע"י Hybrid Tagger (rules-based + LLM-suggester עם human-in-the-loop ב-MVP).

**נוסחת חישוב:** רכיב הפלט של Tagger (raw_filings → staging_filings_parsed → events).

**Timestamp constraint:** ערך ה-feature מבוסס על המידע הזמין ב-`event_observable_at`. אסור להשתמש ב-tagger versions שטרם היו זמינים בעבר; ראה `tagger_version` field לתיעוד.

**Missing strategy:** לא ייתכן חסר. אם Tagger נכשל לחלוטין → האירוע **לא נכנס** למערכת ומסומן `quarantined`.

**סיבתיות:** סוג האירוע מגדיר את ה-prior distribution של תגובת השוק. earnings ≠ regulatory ≠ contract — תגובות סטטיסטיות שונות מהותית.

**Sanity tests:**
- ההתפלגות הכוללת של ערכים שומרת על שונות של ≤10% ברבעון מול הממוצע ההיסטורי.
- אף ערך לא יכול לקבל >40% מהדגימות (אחרת = under-segmentation).
- אף ערך לא יכול לקבל <2% (אחרת = over-segmentation; שקול איחוד).

**סיכוני leakage/overfitting:**
- Tagger המשתמש ב-text שנכתב אחרי האירוע (post-hoc edits בכותרות חדשות).
- שינוי enum mid-flight ללא restart.
- Target encoding ללא smoothing → over-fits לקטגוריות נדירות.

---

### 3.2 `event_type_l2`

| | |
|---|---|
| **Type** | Categorical |
| **Cardinality** | 25-35 ערכים, היררכיים תחת L1 |
| **Encoding** | Target encoding, Bayesian smoothing, k=30 |

**תיאור עסקי:** תת-סיווג מדויק. למשל תחת `earnings`: `beat`, `miss`, `inline`, `restated`. תחת `guidance`: `raise`, `cut`, `reaffirm`, `withdraw`.

**מקור דאטה:** `events.event_subtype`.

**נוסחת חישוב:** Tagger output, level 2.

**Timestamp constraint:** זהה ל-3.1.

**Missing strategy:**
- אם L2 חסר אך L1 קיים → השתמש ב-L1 בלבד; ה-Decision Model רואה L2 כ-`__missing__` (קטגוריה חוקית).
- ב-Memory queries: **fallback אוטומטי ל-L1** אם pool size תחת L2 < 50 (ראה פרק 4.3).

**סיבתיות:** L2 מבדל בין תגובות הפוכות תחת אותה קטגוריה רחבה (earnings beat ≠ earnings miss).

**Sanity tests:**
- כל ערך L2 משויך לערך L1 יחיד (no orphans).
- מינימום 30 דגימות לכל L2 active ב-training window.

**סיכוני leakage/overfitting:**
- Granularity יתר → fragmentation סטטיסטי.
- Tagger המכריע subtype על סמך תגובת השוק (post-event signal).

---

### 3.3 `event_magnitude`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [-5σ, +5σ], capped |

**תיאור עסקי:** עוצמת האירוע מנורמלת לסוג. עבור earnings: surprise = (actual - consensus) / std_historical_surprises. עבור contracts: log10(contract_value_ILS).

**מקור דאטה:**
- earnings: consensus ממקור פיננסי (FactSet/Bloomberg/manual entry ב-MVP).
- contracts: extracted מ-MAYA filing.
- guidance: % change מ-prior guidance.
- אחר: 0 (neutral) אם לא מדיד.

**נוסחת חישוב:**
```
event_magnitude = (raw_value - reference_value) / normalizer
clip(event_magnitude, -5.0, +5.0)
```

הspec של `reference_value` ו-`normalizer` קבוע per event_type_l2 ולא משתנה.

**Timestamp constraint:** רק נתונים זמינים ב-`event_observable_at`. consensus חייב להיות snapshot **לפני** הפרסום.

**Missing strategy:**
- אם consensus לא זמין → ערך = 0 + flag `event_magnitude_missing = True` כ-feature נלווה (binary).
- אם נורמליזציה אינה אפשרית → 0 + flag.

**סיבתיות:** אירוע "גדול" משפיע יותר משעור גודל. surprise של 5σ ≠ surprise של 0.5σ.

**Sanity tests:**
- היסטוגרמה צריכה להיות מרכזת סביב 0 עם זנבות סבירים.
- |event_magnitude| > 5 לפני clipping → flag לבדיקה.
- אם > 5% מהדגימות במצב `missing` → בדיקה של מקור הconsensus.

**סיכוני leakage/overfitting:**
- שימוש ב-consensus אחר-פרסום (post-event revisions).
- normalizer המחושב על כל ההיסטוריה כולל test → use only training-window stats.
- Outliers שלא נחתכו מטים את מקדם הרגרסיה.

---

### 3.4 `event_source_tier`

| | |
|---|---|
| **Type** | Ordinal |
| **Range** | {1, 2, 3, 4} |

**תיאור עסקי:** דירוג אמינות מקור האירוע.

| Tier | מקורות |
|---|---|
| 1 | MAYA / MAGNA (דיווחים רשמיים לבורסה/רשות) |
| 2 | Globes, TheMarker, Calcalist, Bizportal (כותבי כלכלה ראשיים) |
| 3 | Ynet/Walla economy sections, פיננסיים מקומיים נוספים |
| 4 | Social, blogs, telegram, twitter |

**מקור דאטה:** `events.source_tier` (computed at ingestion time via fixed lookup table from `events.source_type`). ה-feature במודל נקרא `event_source_tier`; ה-column ב-DB נקראת `source_tier`. הm aiment מתועד ב-Data Layer §4.3.

**נוסחת חישוב:** Lookup deterministic.

**Timestamp constraint:** Tier קבוע per source. שינוי דירוג של מקור = bump גרסה.

**Missing strategy:** לא ייתכן חסר.

**סיבתיות:** מקור Tier 1 = signal ודאי. Tier 4 = רעש. ה-feature הזה משפיע גם על המודל וגם על Memory weighting (ראה 4.4).

**Sanity tests:**
- 100% מהאירועים מקבלים tier ב-{1,2,3,4}.
- ב-MVP: לא נכנסים אירועי Tier 4 לדאטה (ייכנסו רק אם MVP מוכיח יציבות; ראה 7.6).

**סיכוני leakage/overfitting:**
- שינוי tier של מקור ללא retroactive re-tag → inconsistency.
- LLM tagging המעלה tier על סמך thresholds אחרים מהמוגדרים.

---

### 3.5 `market_cap_log`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [7.5, 11.0] (תאגידים בין 30M ל-100B ש"ח) |

**תיאור עסקי:** log10 של שווי שוק במיליוני ש"ח, נמדד ב-`event_observable_at`.

**מקור דאטה:** `prices_daily.close × shares_outstanding`, snapshot של היום שלפני האירוע.

**נוסחת חישוב:**
```
market_cap_ils = close_t-1 × shares_outstanding_t-1
market_cap_log = log10(market_cap_ils / 1_000_000)
```

**Timestamp constraint:** סגירת היום שקדם ל-`event_observable_at`. אסור close של אותו יום (חלק גדול מהאירועים אינטרא-day → close אותו יום = look-ahead).

**Missing strategy:**
- אם shares_outstanding חסר → fallback למקור המשני (יומי מ-TASE).
- אם עדיין חסר → drop event מהמערכת (לא נכנס ל-features_daily).

**סיבתיות:** small caps מגיבים drastically שונה מ-large caps לאותו אירוע. liquidity, coverage, volatility — הכל פונקציה של גודל.

**Sanity tests:**
- ערכים מתחת ל-7 או מעל 11.5 → flag לבדיקה.
- שינוי יומי של > 0.3 ב-log → flag (כנראה stock split לא מטופל).

**סיכוני leakage/overfitting:**
- שימוש ב-shares_outstanding מעודכן אחרי dilution event שטרם הוכרז.
- חיבור market_cap לאירוע שמשתנה lookahead (mergers).

---

### 3.6 `sector`

| | |
|---|---|
| **Type** | Categorical |
| **Cardinality** | 8 ערכים סגורים |
| **Encoding** | Target encoding, Bayesian smoothing, k=30 |

**תיאור עסקי:** סקטור החברה, באגרגציה גסה מכוונת.

**Enum סגור:**
1. `financials` (בנקים, ביטוח, פיננסים)
2. `real_estate` (יזמית + מניבה)
3. `technology` (תוכנה, סייבר, סמיקונדקטור)
4. `industrials` (תעשייה, נדל"ן יצרני, infrastructure)
5. `consumer` (קמעונאות, מזון, שירותים)
6. `healthcare` (פארמה, מדיקל devices, ביוטק)
7. `energy_utilities` (אנרגיה, חשמל, מים)
8. `communications_media` (תקשורת, מדיה)

**מקור דאטה:** `companies.sector` (curated). מתבסס על TASE classification + manual override במקרי חוסר התאמה.

**נוסחת חישוב:** Lookup, deterministic per company.

**Timestamp constraint:** סקטור בעת `event_observable_at`. אם חברה שינתה סקטור (rare) → bitemporal lookup.

**Missing strategy:** לא ייתכן חסר. חברה ללא סקטור = bug ב-curation; חוסם entry של אירוע.

**סיבתיות:** sector קובע base rates של תגובה. earnings miss בבנק ≠ earnings miss בpharma.

**Sanity tests:**
- אף sector לא יקבל >35% מהדגימות.
- אף sector לא יקבל <3%.

**סיכוני leakage/overfitting:**
- אגרגציה גסה מדי → איבוד signal.
- אגרגציה דקה מדי → fragmentation סטטיסטי.
- שינוי enum mid-flight.

---

### 3.7 `liquidity_score`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | [0, 1] |

**תיאור עסקי:** Composite score לנזילות. מילה אחת על מסחריות.

**מקור דאטה:** `prices_daily` (volume, close), `intraday_quotes_summary` (spread). אם spread data חסר → fallback ל-sector median; ראה Data Layer §3.1 + §4.3.

**נוסחת חישוב:**
```
adv_20 = mean(volume × close, last 20 trading days)
adv_score = clip(log10(adv_20 / 100_000), 0, 1)   # 100K ש"ח → 0; 1B → 1

spread_pct = mean(daily_avg_bid_ask_spread / mid_price, last 20 days)
spread_score = clip(1 - spread_pct / 0.02, 0, 1)  # 2% spread → 0

liquidity_score = 0.6 × adv_score + 0.4 × spread_score
```

חישוב מתבצע EOD לכל יום, ל-`event_observable_at` משתמשים בערך של היום הקודם.

**Timestamp constraint:** rolling 20-day window שמסתיים ביום שלפני `event_observable_at`.

**Missing strategy:**
- אם spread data חסר → liquidity_score = adv_score בלבד (משקלים מתאימים: 1.0 על adv).
- אם volume חסר ב->5 ימים מתוך 20 → drop event.

**סיבתיות:** מניה לא נזילה אינה ניתנת לסחר ב-realistic conditions; כל signal עליה אקדמי.

**Sanity tests:**
- 95% מ-TA-35 שותפים מקבלים liquidity_score > 0.6.
- TA-90 שותפים מקבלים > 0.4 ב-90% מהמקרים.
- ירידה חדה בליקווידיטי (>0.2 ביום אחד) → flag.

**סיכוני leakage/overfitting:**
- שימוש ב-volume של יום האירוע (event causes volume → volume causes prediction).
- שימוש ב-spread averaged over period הכולל את האירוע.

**הערה:** liquidity_score משמש גם כ-feature בDecision Model **וגם** כ-Risk Pre-filter (פרק 6.7). אלה שני שימושים נפרדים.

---

### 3.8 `vix_level`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [10, 50] |

**תיאור עסקי:** VIX level בסגירת היום שלפני האירוע. Proxy ל-global risk regime.

**מקור דאטה:** FRED (`VIXCLS`) או Yahoo (`^VIX`).

**נוסחת חישוב:** raw closing value, ללא transformation.

**Timestamp constraint:** סגירת VIX של trading day t-1 ביחס ל-`event_observable_at`. הקפד על time zone alignment (NY close ≠ TLV close).

**Missing strategy:**
- אם חסר → forward-fill עד 3 ימים. מעבר לכך → drop event.

**סיבתיות:** באירועים זהים, התגובה תלויה במצב הסיכון העולמי. VIX=15 ≠ VIX=35.

**Sanity tests:**
- ערכים מחוץ ל-[8, 80] → flag.
- שינוי יומי >5 נקודות → ודא שזו לא טעות feed.

**סיכוני leakage/overfitting:**
- שימוש ב-VIX של אותו יום מסחר אחרי close → look-ahead.

---

### 3.9 `ta35_trend`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [-0.25, +0.25] |

**תיאור עסקי:** Distance של TA-35 מהממוצע הנע ל-200 ימים, באחוזים.

**מקור דאטה:** TASE indices feed.

**נוסחת חישוב:**
```
ta35_trend = (ta35_close_t-1 - mean(ta35_close, last 200 days)) / mean(ta35_close, last 200 days)
```

**Timestamp constraint:** סגירת t-1.

**Missing strategy:** אם חסר → drop event (חמור).

**סיבתיות:** באירוע positive בשוק bull, התגובה שונה מאשר באירוע positive בשוק bear.

**Sanity tests:**
- |ta35_trend| > 0.4 → flag (תזוזה היסטורית קיצונית).

**סיכוני leakage/overfitting:**
- חישוב MA200 על window הכולל ימים עתידיים.

---

### 3.10 `usdils_5d_change`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [-0.05, +0.05] |

**תיאור עסקי:** שינוי שער USD/ILS ב-5 ימי עסקים אחרונים.

**מקור דאטה:** Bank of Israel API or FRED.

**נוסחת חישוב:**
```
usdils_5d_change = (usdils_t-1 - usdils_t-6) / usdils_t-6
```

**Timestamp constraint:** סגירת t-1.

**Missing strategy:** forward-fill עד 2 ימים; מעבר → drop event.

**סיבתיות:** חברות יצואניות בישראל רגישות ל-FX. תגובה לאירוע exporter תלויה בכיוון השקל.

**Sanity tests:**
- |change| > 0.1 ב-5 ימים → flag (אירוע FX יוצא דופן).

**סיכוני leakage/overfitting:**
- שימוש ב-FX של היום עצמו → look-ahead.

---

### 3.11 `recent_return_20d`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [-0.4, +0.4] |

**תיאור עסקי:** תשואת המניה ב-20 ימי מסחר שקדמו ליום `event_observable_at`.

**מקור דאטה:** `prices_daily.adj_close`.

**נוסחת חישוב:**
```
recent_return_20d = (adj_close_t-1 / adj_close_t-21) - 1
```

**Timestamp constraint:** window מסתיים ב-t-1, מתחיל ב-t-21.

**Missing strategy:**
- אם <15 ימי מסחר תקפים בwindow → drop event.
- otherwise: השתמש בdays available, נורמל למעט.

**סיבתיות:** Momentum/exhaustion. מניה שעלתה 30% ב-month האחרון תגיב אחרת לאירוע positive.

**Sanity tests:**
- |return| > 1.0 → flag (כנראה corporate action לא מטופל).

**סיכוני leakage/overfitting:**
- שימוש ב-non-adjusted prices → tracking של dividend events.
- window הכולל את יום האירוע.

---

### 3.12 `volatility_20d`

| | |
|---|---|
| **Type** | Continuous |
| **Range** | טיפוסי [0.10, 0.80] (annualized) |

**תיאור עסקי:** Realized volatility 20-day, annualized.

**מקור דאטה:** `prices_daily.adj_close`.

**נוסחת חישוב:**
```
daily_returns = log(adj_close_t / adj_close_t-1) for last 20 days ending at t-1
volatility_20d = std(daily_returns) × sqrt(252)
```

**Timestamp constraint:** window מסתיים ב-t-1.

**Missing strategy:**
- אם <15 ימי מסחר → drop event.

**סיבתיות:** מניה תנודתית מגיבה ביתר עוצמה. גם risk premium proxy.

**Sanity tests:**
- volatility > 1.5 → flag.
- volatility < 0.05 → flag (כנראה halted/illiquid).

**סיכוני leakage/overfitting:**
- שימוש ב-realized vol הכולל את יום האירוע.
- חישוב על non-adjusted prices.

---

### 3.13 הוראות אינטגרציה גלובליות

**Standardization:**
פיצ'רים רציפים (`event_magnitude`, `market_cap_log`, `liquidity_score`, `vix_level`, `ta35_trend`, `usdils_5d_change`, `recent_return_20d`, `volatility_20d`) → Z-score על training window בלבד. מחושב מחדש בכל refit.

**Categorical encoding:**
`event_type_l1`, `event_type_l2`, `sector` → target encoding עם Bayesian smoothing (k=30) ב-training; ערך global mean על categories שלא נראו (rare categories at inference).

**Ordinal:**
`event_source_tier` → integer בלבד. אסור one-hot.

**Missing flags:**
כאשר missing strategy מציינת flag binary, ה-flag הוא feature נוסף בכניסה למודל (לא נכלל בספירת 12 הראשיים, אך נכלל ב-input vector אם רלוונטי).

**Interaction features:** **אסור ב-MVP.** ראה פרק 7.1.

---

## 4. Market Memory Specification

Memory היא שכבת **retrieval** — לא prediction. מטרתה להחזיר התפלגות תגובות היסטוריות לאירועים דומים, עם uncertainty quantification.

### 4.1 Pool Definition (Hard Filters)

עבור query מאירוע `Q`, ה-pool ההתחלתי כולל אירועים היסטוריים `H` המקיימים **כל** התנאים:

1. `H.event_type_l1 == Q.event_type_l1`
2. `H.market_cap_bucket == Q.market_cap_bucket` (3 buckets)
3. `H.liquidity_bucket == Q.liquidity_bucket` (3 buckets)
4. `H.event_observable_at < Q.event_observable_at` (cardinal — past only)
5. `H.event_observable_at >= Q.event_observable_at - 15 years`

**Bucketing מוקפא:**

| Bucket | market_cap_log range | liquidity_score range |
|---|---|---|
| Large | ≥ 9.5 (≥ 3.16B ש"ח) | ≥ 0.7 |
| Mid | [8.5, 9.5) | [0.4, 0.7) |
| Small | < 8.5 | < 0.4 |

### 4.2 L2 Filter (Soft)

**אם** `pool_size_after_hard_filters >= 50` ו-`Q.event_type_l2 != null`:
→ הוסף סינון `H.event_type_l2 == Q.event_type_l2`.
→ אם הסינון מוריד pool מתחת ל-50, **חזור ל-L1 בלבד** (fallback).

תיעוד: ה-output של Memory מכיל flag `l2_match: true/false`.

### 4.3 Minimum Pool Size & Fallback Cascade

| Stage | Pool size | פעולה |
|---|---|---|
| 1 | ≥ 50 | ✓ continue ל-similarity ו-k-NN |
| 2 | [30, 50) | ✓ continue, אך הוסף flag `low_pool_size` |
| 3 | [15, 30) | רק את ה-pool כולו (no k-NN), הוסף flag `tiny_pool` |
| 4 | < 15 | **NO OUTPUT.** החזר flag `insufficient_memory`, אין מספרים |

ב-stage 4, ה-Decision Model רץ עצמאית ללא Memory aid. המשתמש רואה flag והודעה.

### 4.4 Similarity Function (לאחר Hard Filters)

על ה-pool שעבר את ה-hard filters, מחושב מרחק לכל אירוע historical `H`:

```
distance(Q, H) = sqrt(
    1.0 × (sector_distance(Q, H))^2 +
    1.0 × ((Q.vix_level - H.vix_level) / σ_vix)^2 +
    1.0 × ((Q.ta35_trend - H.ta35_trend) / σ_ta35)^2 +
    1.0 × ((Q.event_magnitude - H.event_magnitude))^2 +
    0.5 × ((Q.usdils_5d_change - H.usdils_5d_change) / σ_fx)^2
)
```

כאשר:
- `sector_distance = 0` אם sector זהה, `1` אחרת.
- `σ_vix = 8` (mock historical std, מוקפא).
- `σ_ta35 = 0.10` (מוקפא).
- `σ_fx = 0.015` (מוקפא).

**משקלים מוקפאים** ולא ניתנים לכיוונון על backtest. שינוי = bump גרסה.

### 4.5 k-NN Selection

`k = 50` (קבוע, מוקפא).

מהpool, נבחרים ה-50 אירועים עם המרחק הקטן ביותר. אם pool size < 50, נלקח ה-pool כולו.

### 4.6 Sample Weighting

לכל אירוע נבחר מחושב משקל:

```
w(H) = w_recency(H) × w_distance(H) × w_reliability(H)
```

**Recency:**
```
years_ago = (Q.event_observable_at - H.event_observable_at) / 365.25
w_recency = 0.5 ^ (years_ago / 3.0)
```
חצי-חיים: 3 שנים. דגימה מ-15 שנה אחורה ≈ 0.03.

**Distance:**
```
σ_d = median(distance) of pool   # נחשב per-query
w_distance = exp(-0.5 × (distance / σ_d)^2)
```

הערה: σ_d נגזר per-query ולא קבוע. זו אינה כיוונון hyperparameter — זוhi calibration אוטומטית של Gaussian לpool הספציפי.

**Reliability:**
```
tier_to_weight = {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.2}
w_reliability = tier_to_weight[H.event_source_tier]
```

### 4.7 Effective Sample Size (Kish ESS)

```
ESS = (sum of weights)^2 / (sum of squared weights)
```

ESS חייב להיכלל בכל output. אם `ESS < 20` → flag `low_ess` (ראה 6.1).

### 4.8 Output Schema

```json
{
  "query_id": "<UUID>",
  "memory_version": "1.0",
  "timestamp": "<UTC>",
  
  "pool": {
    "size_initial": <int>,
    "size_after_l2": <int|null>,
    "size_returned": <int>,
    "stage": <1|2|3|4>,
    "l2_match": <bool>
  },
  
  "weights": {
    "ess": <float>,
    "recency_weighted_share_last_3y": <float>,
    "tier1_weighted_share": <float>
  },
  
  "outputs": {
    "median_return_5d": <float|null>,
    "p10_return_5d": <float|null>,
    "p90_return_5d": <float|null>,
    "median_return_10d": <float|null>,
    "p10_return_10d": <float|null>,
    "p90_return_10d": <float|null>,
    "downside_prob_5d": <float|null>,    // P(return < -2%)
    "downside_prob_10d": <float|null>
  },
  
  "flags": [
    "insufficient_memory" | "low_pool_size" | "tiny_pool" |
    "low_ess" | "tier1_underrepresented" | "old_data_dominant"
  ]
}
```

**`null` outputs:** מתקבלים אך ורק כש-stage = 4 (insufficient_memory).

**Flags additional:**
- `tier1_underrepresented`: tier1_weighted_share < 0.4 → דגימות פחות אמינות שולטות.
- `old_data_dominant`: recency_weighted_share_last_3y < 0.25 → רוב הסיגנל מ-history רחוקה.

### 4.9 Hyperparameters Frozen Table

| Parameter | Value | רציונל |
|---|---|---|
| k (k-NN) | 50 | balance בין resolution ל-coverage |
| Pool min stage 1 | 50 | minimum לסטטיסטיקה הגיונית |
| Pool fallback to stage 4 | <15 | מתחת לכך אין משמעות |
| Recency half-life | 3.0 שנים | balance regime change vs sample size |
| History window | 15 שנים | TASE has reliable data depth |
| σ_vix | 8 | scaling factor |
| σ_ta35 | 0.10 | scaling factor |
| σ_fx | 0.015 | scaling factor |
| Tier weights | {1.0, 0.8, 0.5, 0.2} | gradient רחב, לא flat |
| Downside threshold | -0.02 | 2% loss = meaningful drawdown |
| Output horizons | 5d, 10d | matches strategy horizon |

**אזהרה:** ערכים אלה מוקפאים ב-V1. שינוי = bump גרסה + restart validation. **אסור** לבצע grid search על ערכים אלה ולבחור את "המנצח" — זה overfitting ישיר על history שנעשתה זמינה.

---

## 5. Decision Model — Constraints

מודל ההחלטה מפורט במסמך נפרד (`DECISION_MODEL_SPEC_V1.md`), אך החובות החוקתיות שלו מוגדרות פה:

### 5.1 Architecture

- אלגוריתם: Gradient Boosting (LightGBM) **או** Logistic Regression with Elastic Net.
- בחירה תיקבע ב-MVP על בסיס validation performance, **אך נעולה לאחר בחירה ראשונה**.

### 5.2 Hyperparameters (אם LightGBM)

```
max_depth: 3
min_data_in_leaf: 50
learning_rate: 0.03
n_estimators: 500 with early_stopping_rounds=50
colsample_bytree: 0.7
subsample: 0.7
reg_alpha: 0.1
reg_lambda: 1.0
```

### 5.3 Hyperparameters (אם Logistic Regression)

```
penalty: elastic_net
l1_ratio: 0.5
C: 1.0 (ראשוני; ניתן לכיוונון על validation בלבד, לא test)
```

### 5.4 Target

Binary: `target = 1 if forward_return_5d > total_costs × 1.5 else 0`

```
total_costs = commission_round_trip + slippage_round_trip + (spread_pct × 2)
            = 0.0020 + 0.0010 + (spread_pct × 2)
            = 0.0030 + (spread_pct × 2)
```

כאשר `spread_pct` הוא ה-bid-ask spread של המניה ב-`t-1`, נלקח מ-`features_at_event.features.spread_pct` (ראה Data Layer §4.4).

ה-1.5× margin הוא safety margin מעל transaction costs. תואם ל-§8.4 ול-Decision Model §3.1.

### 5.5 Calibration

לאחר אימון: **isotonic regression** ב-validation set להתאמת probabilities. ה-output הסופי הוא calibrated probability.

### 5.6 Decision Threshold

`p > 0.55` → take.
`p ≤ 0.55` → skip.

הסף נקבע מראש ולא מותאם על test.

### 5.7 Confidence Interval

Bootstrap-based: 100 models מאומנים על subsamples של training; per prediction מתקבלים 100 probabilities. CI = [p10, p90] של ההתפלגות.

**Hard rule:** אם `CI` חוצה את `0.5` (כלומר p10 < 0.5 < p90), ההחלטה היא **skip** ללא תלות בpoint estimate.

### 5.8 Memory לא feature

ראה פרק 7.4. Memory output אינו נכלל ב-feature vector.

---

## 6. Failure Handling

מטריצת תגובה מלאה. כל מצב = פעולה דטרמיניסטית, ללא שיקול דעת בזמן ריצה.

### 6.1 `effective_n < 20` (ESS נמוך)

**מצב:** Memory החזירה pool עם משקלים מוטים מאוד.

**פעולה:**
1. Memory output מוחזר עם flag `low_ess`.
2. Decision Model רץ רגיל (Memory לא feature).
3. **ב-presentation למשתמש:** numbers דועכים (greyed out) + הודעה "Memory pool dominated by few samples — interpret with caution."
4. אם גם CI של Decision Model רחב (p90-p10 > 0.30) → **auto-skip** ללא תלות במשתמש.

### 6.2 Pool size קטן מדי (`<15`)

**מצב:** stage 4. אין דגימות היסטוריות מספיקות.

**פעולה:**
1. Memory output: כל המספרים `null`, flag `insufficient_memory`.
2. Decision Model רץ, אך **decision threshold מוקשח**: take רק אם `p > 0.65` (במקום 0.55).
3. הודעה למשתמש: "No historical comparable events. Decision based on model alone."

### 6.3 פיצ'ר חסר

**מצב:** feature מסוים לא ניתן לחישוב.

**פעולה לפי feature (ראה גם missing strategies בפרק 3):**

| Feature | אם חסר |
|---|---|
| event_type_l1 | DROP event |
| event_type_l2 | continue, flag at L1 |
| event_magnitude | value=0, add binary missing flag |
| event_source_tier | DROP event |
| market_cap_log | DROP event |
| sector | DROP event |
| liquidity_score | recompute on adv only; if <30% of feature available, DROP |
| vix_level | forward-fill ≤3 days, else DROP |
| ta35_trend | DROP event |
| usdils_5d_change | forward-fill ≤2 days, else DROP |
| recent_return_20d | DROP event |
| volatility_20d | DROP event |

DROP event = אירוע לא נכנס למערכת לעיבוד; נרשם בlog `dropped_events`.

### 6.4 Decision CI חוצה 50%

**מצב:** `p10 < 0.5 < p90`.

**פעולה:** auto-skip. החלטה דטרמיניסטית, ללא תלות בpoint estimate.

ב-paper trading log: רישום עם reason `ci_crosses_threshold`.

### 6.5 Data source לא אמין

**מצב:** מקור דאטה ראשי נופל / מחזיר staleness > threshold.

**פעולה:**

| מקור | Threshold | פעולה |
|---|---|---|
| Prices feed (TASE) | >2 ימי איחור | freeze decisions for affected universe |
| MAYA | >6 שעות | continue with warning, flag affected events |
| News RSS | >30 דקות | continue, flag |
| FRED (VIX, USD/ILS) | >3 ימים | freeze decisions |

"Freeze decisions" = no new take recommendations. existing positions remain (paper trading log).

### 6.6 Event score נמוך (Tagger confidence)

**מצב:** Tagger confidence < 0.6.

**פעולה:**
1. Event נכנס למערכת אך מסומן `low_tagger_confidence`.
2. ב-MVP: אירועים עם tagger confidence < 0.6 **לא מייצרים החלטות**, רק נרשמים לreview ידני.
3. ב-Memory: לא נכללים בpool (לא רוצים להזיק לדאטה ההיסטורית).

### 6.7 Liquidity Pre-filter נכשל

**מצב:** `liquidity_score < 0.4` בעת הופעת אירוע.

**פעולה:**
1. אירוע נרשם, אך **לא מועבר ל-Decision Model**.
2. סטטוס: `pre_filtered_illiquid`.
3. Memory queries דווקא **כן** ירוצו (אם המשתמש רוצה לראות historical context), אך ללא decision.

### 6.8 Memory ו-Decision Model סותרים

**מצב:** Decision Model אומר `take` (p > 0.55) אך Memory `median_return_5d < -0.005`. או הפוך.

**פעולה:**
1. **לא** override אוטומטי. שני ה-outputs מוצגים למשתמש.
2. Flag `model_memory_disagreement` ב-presentation.
3. Decision rule paper-trading: take **רק** אם המשתמש מאשר ידנית. אחרת skip.
4. סתירות נרשמות לlog נפרד — עליהן יורצו בדיקות מקיפות ברביעון.

**רציונל:** סתירה היא signal — לפעמים המודל לוכד דפוס שה-Memory לא רואה, ולפעמים Memory מציגה reality שהמודל miscalibrated. ב-MVP, אנו לא יודעים איזה קייס שכיח יותר. נצבור דאטה.

---

## 7. Design Constraints (Hard Rules)

חוקתיות. שינוי דורש V2.

### 7.1 No Interaction Features

ב-MVP ה-input vector מכיל רק את 12 הפיצ'רים + missing flags. **אסור** ליצור features ידניים מסוג `event_type × sector` או `vix × magnitude`. אם הGradient Boosting יזהה interactions — מצוין; הוא עושה זאת בעצמו במחיר רגולריזציה. ידני = overfitting.

### 7.2 No Tuning of Memory Hyperparameters on Backtest

כל הערכים בטבלת 4.9 מוקפאים. **אסור** להריץ grid search על Memory hyperparameters ולבחור את הקומבינציה ש"עובדת הכי טוב". זה meta-overfitting ישיר.

שינוי לגיטימי: אם out-of-sample paper trading מראה ש-Memory לא עוזרת בכלל (downside_prob לא מתואמת עם תוצאות), שקול amendment בגרסה הבאה — עם justification מנומק.

### 7.3 No Memory as Feature

Memory output לא נכנס ל-Decision Model כ-input. הם שני מסלולים מקבילים.

**רציונל:** אם Memory output הוא feature, יש circular dependency: המודל לומד "Memory מצביעה positive → I predict positive" וה-feedback loop יוצר false confidence. בנוסף, Memory בנויה על אירועים שמהם מאומן המודל — דאטה leakage עקיף.

### 7.4 No LLM in Decision Path

LLM משמש רק לשני תפקידים:
1. **תיוג** אירועים (input layer): suggester ל-event_type_l1/l2, תמיד עם human review ב-MVP.
2. **הסבר** (output layer): מסביר למשתמש למה ההחלטה כפי שהיא, מבוסס על feature importances.

**אסור:**
- LLM שמקבל סיגנלים ופולט החלטה.
- LLM שקובע weights או thresholds.
- LLM שמוציא probability scores.

### 7.5 Frozen Universe for MVP

TA-35 + TA-90 בלבד. אסור להוסיף Yeter (small caps) במהלך MVP. גם אם מודל מצוין על TA-35 לא יעבוד בהכרח על Yeter (regime statistical שונה).

### 7.6 No Smart Money in MVP

קומפוננטת Smart Money מתועדת אך **לא מוטמעת**. תוכל להיות מוטמעת רק לאחר ש-MVP עומד בפרק 9 promotion criteria.

### 7.7 No Intraday

החלטות ב-EOD בלבד. intraday data משמשת רק ל-features (e.g., bid-ask spread averaging).

### 7.8 No Auto-Execution

בכל שלב MVP. אישור ידני אנושי לכל פוזיציה (גם paper trading). מטרה: לשמור על משוב אנושי ולמנוע תקלות ממונעות אוטומציה.

### 7.9 No Live Money in MVP

12 חודשים paper trading מינימום. ללא יוצא מן הכלל.

### 7.10 No Public/Third-Party Use

המערכת לשימוש אישי בלבד עד הוכחת performance + השלמת בדיקות compliance regulatory (חוק הסדרת העיסוק בייעוץ השקעות).

---

## 8. Validation Framework

### 8.1 Walk-Forward Setup

```
Train window: 5 שנים
[5 trading days embargo]
Validation window: 1 שנה
[5 trading days embargo]
Test window: 1 שנה
Refit cadence: כל 6 חודשים
```

**הערה: 5 trading days, לא calendar days.** Embargo מחושב דרך `tase_trading_calendar` (Data Layer §3.6). פירוט implementation ב-Decision Model §4.3.

**רציונל ל-embargo:** מונע leakage מאירועים שמתחילים בtrain ומשפיעים ל-test (e.g., חדשות שהשפיעו 3 ימים).

### 8.2 Metrics נמדדים

על test set:

| Metric | Threshold |
|---|---|
| AUC-ROC | ≥ 0.55 (otherwise no edge) |
| Precision @ p>0.55 | ≥ 0.55 |
| Brier score | ≤ 0.245 |
| Sharpe (paper trading) | ≥ 0.5 ב-OOS |
| Max drawdown | ≤ 20% |
| Hit rate | ≥ 52% |
| Avg return per take (after costs) | ≥ +0.5% |

### 8.3 Sample Weighting in Training

Exponential decay: `weight = 0.5 ^ (years_old / 3)`.
מבטיח שדגימות עדכניות חשובות יותר מבלי לקצוץ history.

### 8.4 Transaction Costs Model

כל simulation/backtest כולל:
- **Commission:** 0.10% per side (0.20% round-trip).
- **Spread:** 0.5 × spread_pct של המניה ב-event time, per side.
- **Slippage assumption:** 0.05% per side.
- **סך כולל מינימלי:** 0.30% round-trip, יכול להיות עד 1% במניות לא נזילות.

החלטות take רק כאשר expected return > total costs × 1.5 (margin of safety).

### 8.5 בדיקות Anti-Leakage

לפני כל deployment של מודל חדש:

1. **Random label test:** הרץ אימון על labels מעורבבים. AUC צריך להיות ≈ 0.50. אם > 0.55 → leakage.
2. **Future-only feature test:** אסור פיצ'ר עם timestamp > event_observable_at. אוטומטית בtests.
3. **Forward-shift consistency:** הסט את כל ה-event timestamps בשבוע קדימה. תוצאות חייבות להישאר בכיוון הצפוי.

### 8.6 Test Set Sanctity

Test set **לעולם** לא נראה במהלך development חוץ מבסוף. לאחר הצצה — ה-window זה זוהם וצריך window חדש.

תיעוד: `test_window_views.log` — כל view לtest window (legitimate או לא) מתועד.

---

## 9. Failure Criteria — Kill Switches

### 9.1 Soft Kill (Pause + Investigate)

מתעוררים כאשר:
- Sharpe ב-rolling 6 months < 0.3.
- Max drawdown > 15%.
- Hit rate < 50% over 50+ trades.

**פעולה:** עוצרים החלטות חדשות. מנתחים. תיקון אפשרי = bump גרסה. אם לא נמצא תיקון → הפעלה מחדש דורשת justification ו-validation מחדש על window חדש.

### 9.2 Hard Kill (Project End)

מתעוררים כאשר:
- 12 חודשי paper trading משלימים עם Sharpe < 0.0 — **מערכת לא עובדת.**
- Live performance < 50% של backtest performance באותו window — overfitting הוכח.
- עדות חד-משמעית ל-leakage בdata.
- שינוי regulatory שאוסר על המערכת.

**פעולה:** מערכת מסיימת התפקדות. החלטה לא שיקול דעת — מתועדת מראש.

### 9.3 Promotion Criteria from Paper to Live

לאחר 12 חודשים מינימום:
- Sharpe ≥ 0.6 ב-rolling 12 months.
- Max drawdown ≤ 15%.
- Hit rate ≥ 53%.
- ≥ 100 trades (סטטיסטית משמעותי).
- אין flags של leakage או source instability.
- compliance review השלמה.

הענקת promotion **לא מבטיחה** גודל פוזיציה. גודל ראשוני = 25% מ-target capital. עליה הדרגתית רק לאחר 6 חודשים נוספים של live performance המאמתים את ה-paper trading.

---

## 10. Change Protocol

### 10.1 סוגי שינויים

| סוג | דוגמה | דרישות |
|---|---|---|
| Editorial | typo, formatting | inline edit, no version bump |
| Clarification | הוספת הסבר ללא שינוי לוגיקה | minor version bump (V1.0 → V1.1) |
| Substantive | feature addition/removal/changes | major version bump (V1.0 → V2.0), restart validation |
| Failure handling | תוספת/שינוי בpolicy 6.x | minor version bump |
| Constraint | הסרה/הוספה של 7.x rule | major version bump |

### 10.2 Procedure לשינוי substantive

1. כתיבת `AMENDMENT_<new_version>.md` המתאר:
   - מה משתנה.
   - למה (justification מבוסס דאטה, לא תחושה).
   - איזה risk נוצר (overfitting, leakage, etc.) ואיך מנוטרל.
   - מה ה-validation framework החדש.
2. Tag של version חדש בrepo.
3. Reset של validation: train/val/test windows חדשים, אסור window שראה את הדאטה הישנה.
4. תיעוד תאריך החלת המעבר.

### 10.3 דברים שלא יהיו amendable

ל-V1, אלה עקרונות ליבה שלא ניתנים לשינוי באף amendment של V1.x:
- 7.3: No Memory as Feature.
- 7.4: No LLM in Decision Path.
- 7.8: No Auto-Execution.
- 7.9: No Live Money in MVP.

שינוי שלהם מחייב V2.

---

## 11. Glossary (התאמת מונחים)

| מונח | הגדרה |
|---|---|
| **Event** | יחידת מידע מתויגת על אירוע תאגידי או שוקי, עם timestamp ל-observable_at |
| **observable_at** | timestamp שבו המערכת יכלה (לראשונה) לראות את האירוע. הזמן הקריטי ל-anti-leakage |
| **claimed_at** | timestamp שהמקור טוען עליו. נרשם לcomparison אך לא משמש להחלטות |
| **Pool** | אירועים היסטוריים העוברים את ה-hard filters של Memory query |
| **ESS** | Effective Sample Size = (Σw)² / Σw² |
| **Take/Skip** | פלט בינארי של Decision Model |
| **CI** | Confidence Interval של probability prediction, [p10, p90] |
| **Tier** | דירוג אמינות מקור (1-4) |
| **Bucket** | חלוקה דיסקרטית ל-buckets (market cap, liquidity) |
| **Refit** | אימון מחדש של Decision Model עם training window עדכני |
| **Embargo** | פער זמן בין train ל-test למניעת leakage |
| **Drop event** | אירוע לא נכנס למערכת (validation failure) |
| **Quarantine** | אירוע נכנס למערכת אך לא משמש להחלטות |
| **Soft/Hard Kill** | סוגי מנגנוני עצירה (פרק 9) |

---

## 12. Signatures

ה-Contract הזה נחתם וחל מ:

```
Owner:        ____________________   Date: __________
Version:      V1.0.1
Document hash (SHA-256): __________________________________
Repo location: TECHNICAL_CONTRACT_V1.0.1.md
Amendments applied: AMENDMENT_V1.0.1.md
```

---

**END OF CONTRACT V1.0.1**
