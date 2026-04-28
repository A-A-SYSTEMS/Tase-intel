# DATA LAYER SPECIFICATION V1.0.1 — AI Trading Intelligence System for TASE

> **Status:** ACTIVE — V1.0.1
> **Effective Date:** ____________
> **Owner:** ____________
> **Companion to:** `TECHNICAL_CONTRACT_V1.0.1.md` (חובה לקרוא לפני)
> **Last Amended:** V1.0 → V1.0.1 (see `AMENDMENT_V1.0.1.md`)

---

## 0. Document Status & Authority

מסמך זה מגדיר את **שכבת הדאטה הביצועית** של המערכת. הוא subordinate ל-`TECHNICAL_CONTRACT_V1.md` — כל סתירה בין המסמכים → ה-Contract מנצח, וה-spec הזה מתעדכן.

**כללי שינוי:**

1. שינוי **שכבת raw או lineage** (פרק 3, 7) דורש major bump (V1 → V2). אלה immutable foundations.
2. שינוי **schema של curated tables** (פרק 4) דורש migration plan + bump גרסה.
3. שינוי **ingestion schedules או thresholds** (פרק 6, 9) דורש minor bump (V1.0 → V1.1) + log entry.
4. שינוי **anti-leakage rules** (פרק 8) **אסור** ב-V1.x. דורש V2 + restart validation.

**עיקרון מנחה:** Raw הוא הברונזה — שום דבר לא נמחק, שום דבר לא מתעדכן. כל שאר השכבות נגזרות ממנו דרך transformations versioned.

---

## 1. Mission & Scope

### 1.1 מה השכבה צריכה לספק

- **Reproducibility:** ריצה של backtest על תאריך X תיתן אותה תוצאה היום, מחר, ובעוד שנה.
- **As-of correctness:** query על "מה ידעתי ב-2024-03-15 בשעה 15:30" יחזיר בדיוק את המידע שהיה זמין באותו רגע — לא יותר, לא פחות.
- **Bias-free history:** כולל delisted, mergers, name changes, splits, dividends — בלי survivorship bias ובלי look-ahead.
- **Lineage:** לכל ערך curated → trace חוזר ל-raw record + parser version + ingestion timestamp.
- **Robustness:** נפילת מקור לא משביתה את המערכת; reconciliation אוטומטית מזהה סתירות.

### 1.2 מה היא לא צריכה לספק (ב-V1)

- Real-time / sub-minute updates (EOD בלבד; ראה Contract 7.7).
- Streaming infrastructure (Kafka/Kinesis) — overkill ל-MVP.
- Multi-region replication.
- Public API / external consumers.

### 1.3 Universe של דאטה

| תחום | היקף ראשוני |
|---|---|
| Active companies | ~125 (TA-35 + TA-90) |
| Delisted companies | כל TA-100 historical members מ-2010 ואילך (~150-200) |
| History depth | 15 שנים rolling (יישמר עד 20) |
| Daily price records | ~7M שורות אחרי 15 שנה |
| Filings (MAYA + MAGNA) | ~50K-100K מסמכים מצטברים |
| News headlines | ~500K-1M מצטברים |
| Macro time series | ~10 series, daily |

**גודל אחסון משוער (5 שנים):** 30-60 GB (raw blobs) + ~5 GB (PostgreSQL).

---

## 2. Tech Stack — Frozen Choices

| תפקיד | כלי | גרסה מינימלית | רציונל |
|---|---|---|---|
| RDBMS | PostgreSQL | 15+ | יציבות, native JSON, partial indexes |
| Time series ext. | TimescaleDB | 2.13+ | hypertables, compression, native PG |
| Object storage (raw) | Local FS → S3-compatible | — | filesystem ב-MVP, נתיב path מוכן ל-cloud |
| Backup | pg_dump + WAL archiving | — | RPO 5 דק', RTO שעתיים |
| Off-site backup | Backblaze B2 / Wasabi | — | $5-7/TB/חודש, S3 API |
| Orchestration | Prefect | 2.x | Python-native, simpler than Airflow |
| Migration | Alembic | — | versioned schema changes |
| Validation | Pydantic + Great Expectations | — | schema (Pydantic) + data quality (GE) |
| Monitoring | Grafana + PostgreSQL exporter | — | dashboards on top of curated tables |

**Frozen.** Stack changes = V2 bump.

---

## 3. Data Sources

עבור כל מקור: tier (חיוני/חשוב/אופציונלי), method, frequency, fallback policy.

### 3.1 TASE Prices & Indices (Tier 1 — חיוני)

| | |
|---|---|
| **Primary source** | TASE Data Hub API (data.tase.co.il) |
| **Method** | REST API, authenticated |
| **Frequency** | EOD daily, 19:00 IST + 22:00 IST (re-fetch ל-adjustments) |
| **Coverage** | OHLCV, volume, market cap, shares outstanding, indices (TA-35, TA-90, TA-125), corporate actions |
| **Cost** | תלוי tier — ~₪500-2,000/חודש ל-MVP plan |
| **Includes delisted** | כן (חיוני) |
| **Fallback primary** | EODHD (eodhd.com) — `$20-50/month`, includes delisted |
| **Fallback secondary** | Yahoo Finance (`yfinance`) — חינם, חלקי, לcross-validation בלבד |
| **Critical fields** | `business_date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `shares_outstanding`, `currency` |

**הערות:**
- `adj_close` חייב להגיע ביחד עם `close` raw. אם המקור לא מספק — drop source.
- ספרד נתונים (bid-ask) לא תמיד זמין מ-TASE EOD. אחסון נפרד ב-`intraday_quotes_summary` (ראה §4.3).
- **ב-MVP fallback policy לspread חסר:**
  1. **Tier 1:** sector median spread של 60 הימים האחרונים (marked `is_synthetic = TRUE`).
  2. **Tier 2:** אם אין מספיק data ל-sector median → spread = 0.005 (50 bps), conservative default (`is_synthetic = TRUE`).
  3. ב-V2: שיקול לקנות data feed מובנה.
- אם spread נכנס כ-synthetic → flag `spread_is_synthetic = 1` ב-`features_at_event.features`.

### 3.2 MAYA Filings (Tier 1 — חיוני)

| | |
|---|---|
| **Primary source** | MAYA archive (mayafiles.tase.co.il) |
| **Method** | Web scraping (אין API ציבורי) |
| **Frequency** | Polling כל 30 דק' בשעות 09:00-17:30 IST; כל שעתיים אחר כך |
| **Format** | רוב PDF, חלק HTML, מעט XBRL (דוחות כספיים מ-2018) |
| **Coverage** | דיווחים מיידיים, דוחות כספיים, מצגות |
| **Fallback** | אין — זה המקור הרשמי |
| **Critical fields** | `filing_id`, `company_id` (TASE), `filing_type`, `published_at_tase`, `document_url` |

**הערות:**
- אין SLA. הסקרייפר חייב להיות robust ל-DOM changes.
- שמור raw HTML של רשימת הדיווחים יומית — זה ה-ground truth שלך.
- PDFs הם blobs; שומרים בfilesystem, רק metadata + path בDB.
- יש דיווחים בסיווג "טיוטה" — לא נכנסים למערכת ההחלטות.

### 3.3 MAGNA Filings (Tier 2 — חשוב)

| | |
|---|---|
| **Primary source** | MAGNA — רשות ני"ע (magna.isa.gov.il) |
| **Method** | Scraping; יש endpoint XML חלקי |
| **Frequency** | Polling כל שעתיים |
| **Coverage** | חופף משמעותית עם MAYA, עם הוספות (בעלי עניין, שינויים בהון) |
| **Fallback** | MAYA (חופף ~80%) |

**יחס למאיה:** לרוב, MAGNA הוא complement. ב-MVP — **MAYA primary, MAGNA secondary**. רק דיווחים שלא הופיעו ב-MAYA נכנסים מ-MAGNA. Reconciliation יומי מאתר חוסרים.

### 3.4 News RSS (Tier 1 — חיוני, אך חלקי)

| | |
|---|---|
| **Primary sources** | Globes RSS, TheMarker RSS, Calcalist RSS, Bizportal RSS, Ynet Economy RSS |
| **Method** | RSS polling |
| **Frequency** | כל 15 דק' (24/7) |
| **Coverage** | Headlines + summary, **לא** full text |
| **Cost** | חינם |
| **Fallback** | אין — multiple sources הוא ה-redundancy |
| **Critical fields** | `headline`, `summary`, `url`, `publisher_claimed_at`, `fetched_at` |

**הערות קריטיות:**
- `fetched_at` (timestamp שלנו, UTC) הוא הקובע ל-anti-leakage. `publisher_claimed_at` הוא metadata.
- כותרות עוברות עריכה retroactively — שמור **כל גרסה** (hash על headline; אם שונה → record חדש).
- חלק מה-RSS feeds מספקים פחות מ-50 פריטים אחרונים — polling בתדירות נדרש כדי לא לפספס.
- **אסור scraping של full article body** ב-MVP (publishers blocking, legal).

### 3.5 Macro & FX (Tier 1 — חיוני)

| Source | Series | Frequency | Method |
|---|---|---|---|
| FRED | `VIXCLS`, `SP500`, `DTWEXBGS` (DXY proxy) | Daily, 23:00 IST | API (`fredapi`) |
| Bank of Israel | USD/ILS official, BoI rate | Daily, 18:00 IST | API (boi.org.il) |
| Yahoo Finance | `^VIX`, `^GSPC` | Daily | Backup ל-FRED |

**הערות:**
- Time zone alignment קריטי: NY close ≠ TLV close. שמור timestamps ב-UTC ותרגם ב-query.
- USD/ILS — שתי גרסאות: BoI official (יומי, פעם ביום) + market rate (intraday). לcontract → BoI official.
- VIX ב-FRED מתעדכן ב-T+1 לעיתים. אם חסר ב-T+0 → forward-fill ≤3 ימים (Contract 6.3).

### 3.6 Reference Data — TASE Trading Calendar (Tier 1)

| | |
|---|---|
| **Source** | TASE official + manual maintenance |
| **Method** | Yearly download + delta updates |
| **Coverage** | Trading days, half-days, market closures (חגים, ימי שבתון) |
| **Critical:** | every completeness check אצלנו תלוי בלוח זה |

תמיד יש לוח שנה לשנה הקרובה לפחות. שמור as table `tase_trading_calendar`.

### 3.7 Reference Data — Sector & Index Membership History (Tier 1)

| | |
|---|---|
| **Source** | TASE classifications + manual override |
| **Method** | Snapshot חודשי + bitemporal tracking |
| **Critical:** | חברה שיצאה מTA-35 לפני 3 שנים — חייבת להיות מסומנת כך ב-2021, לא כיום |

### 3.8 מקורות **לא** כלולים ב-V1

(תיעוד ל-Smart Money עתידי / V2)

- 13F-equivalent ישראלי (דיווחי גופים מוסדיים — חלקי במאיה).
- Trading volume by venue.
- Options/derivatives data.
- Twitter/X firehose.
- Telegram channels.
- Dark pool data (לא קיים בישראל באופן מאורגן).

---

## 4. Database Schema

**Convention:**
- כל טבלה: `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- כל טבלה curated/staging: `record_version INT DEFAULT 1`.
- Bitemporal tables: `valid_from`, `valid_until`, `recorded_at`, `superseded_at` (ראה פרק 5).
- UUIDs לכל primary keys ב-curated; BIGSERIAL ב-raw (high volume, monotonic).
- Timestamps תמיד `TIMESTAMPTZ`, UTC-stored.
- Dates (`business_date`) ב-`DATE` type, IST interpretation.

### 4.1 Raw Layer (Immutable, Append-Only)

```sql
-- ============================================================
-- raw_price_snapshots
-- ============================================================
CREATE TABLE raw_price_snapshots (
    ingestion_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                 -- 'tase_api' | 'eodhd' | 'yfinance'
    source_version TEXT NOT NULL,         -- API/scraper version
    fetched_at TIMESTAMPTZ NOT NULL,      -- UTC
    business_date DATE NOT NULL,
    raw_payload JSONB NOT NULL,           -- exact source response
    payload_hash TEXT NOT NULL,           -- SHA-256 of normalized payload
    request_metadata JSONB,               -- URL, headers, response time
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, business_date, payload_hash)
);

CREATE INDEX idx_raw_prices_source_date ON raw_price_snapshots(source, business_date);
CREATE INDEX idx_raw_prices_fetched ON raw_price_snapshots(fetched_at DESC);

-- ============================================================
-- raw_filings (MAYA / MAGNA)
-- ============================================================
CREATE TABLE raw_filings (
    ingestion_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                 -- 'maya' | 'magna'
    source_doc_id TEXT NOT NULL,          -- ID at the source
    fetched_at TIMESTAMPTZ NOT NULL,
    filing_published_at TIMESTAMPTZ,      -- as claimed by source
    document_url TEXT NOT NULL,
    document_blob_path TEXT NOT NULL,     -- /data/raw/{source}/{yyyy}/{mm}/{dd}/{filename}
    document_hash TEXT NOT NULL,          -- SHA-256 of blob
    document_mime_type TEXT,              -- 'application/pdf', 'text/html'
    raw_metadata JSONB,                   -- everything else from source
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, source_doc_id, document_hash)
);

CREATE INDEX idx_raw_filings_source_date ON raw_filings(source, filing_published_at);
CREATE INDEX idx_raw_filings_fetched ON raw_filings(fetched_at DESC);

-- ============================================================
-- raw_news
-- ============================================================
CREATE TABLE raw_news (
    ingestion_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                 -- 'globes_rss' | 'themarker_rss' | ...
    fetched_at TIMESTAMPTZ NOT NULL,      -- OUR timestamp, NOT publisher's
    publisher_claimed_at TIMESTAMPTZ,     -- as RSS reports
    headline TEXT NOT NULL,
    summary TEXT,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    headline_hash TEXT NOT NULL,          -- detect retroactive edits
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, url_hash, headline_hash)
);

-- key constraint: same (source, url) with different headline_hash
-- = retroactive edit, both records preserved
CREATE INDEX idx_raw_news_url ON raw_news(url_hash);
CREATE INDEX idx_raw_news_fetched ON raw_news(fetched_at DESC);
CREATE INDEX idx_raw_news_source_date ON raw_news(source, publisher_claimed_at);

-- ============================================================
-- raw_macro
-- ============================================================
CREATE TABLE raw_macro (
    ingestion_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                 -- 'fred' | 'boi' | 'yahoo'
    series_id TEXT NOT NULL,              -- 'VIXCLS' | 'USDILS_BOI' | ...
    fetched_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    value NUMERIC,
    value_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, series_id, business_date, fetched_at)
);

CREATE INDEX idx_raw_macro_series ON raw_macro(source, series_id, business_date);
```

**עיקרון:** raw tables אף פעם **לא** מתעדכנים. אם source מתקן ערך, נכנס record חדש עם `fetched_at` חדש; ההיסטוריה נשמרת.

### 4.2 Staging Layer (Versioned Transformations)

```sql
-- ============================================================
-- staging_filings_parsed
-- ============================================================
CREATE TABLE staging_filings_parsed (
    parsed_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_id BIGINT NOT NULL REFERENCES raw_filings(ingestion_id),
    parser_version TEXT NOT NULL,        -- 'v1.0' | 'v1.1' | ...
    parsed_at TIMESTAMPTZ NOT NULL,
    filing_type TEXT,                    -- 'earnings' | 'guidance' | ...
    filing_subtype TEXT,
    reported_company_name TEXT,
    reported_ticker TEXT,
    reported_isin TEXT,
    extracted_fields JSONB,              -- structured extracted data
    parse_confidence NUMERIC,            -- 0..1
    parse_warnings TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(ingestion_id, parser_version)
);

CREATE INDEX idx_staging_filings_ingestion ON staging_filings_parsed(ingestion_id);
CREATE INDEX idx_staging_filings_parser ON staging_filings_parsed(parser_version);

-- ============================================================
-- staging_news_tagged
-- ============================================================
CREATE TABLE staging_news_tagged (
    tagged_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_id BIGINT NOT NULL REFERENCES raw_news(ingestion_id),
    tagger_version TEXT NOT NULL,        -- 'rules_v1.0+dictabert_v1.0'
    tagged_at TIMESTAMPTZ NOT NULL,
    is_relevant BOOLEAN,                 -- did the tagger judge this is a tradable event
    event_type_l1 TEXT,
    event_type_l2 TEXT,
    company_candidates JSONB,            -- [{company_id, confidence}, ...]
    tagger_confidence NUMERIC,
    tagger_warnings TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(ingestion_id, tagger_version)
);

-- ============================================================
-- staging_prices_normalized
-- ============================================================
-- Optional intermediate; can skip if normalization is trivial.
-- Keep for cases of complex multi-source merging.
CREATE TABLE staging_prices_normalized (
    normalized_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID,                     -- after entity resolution
    business_date DATE NOT NULL,
    primary_source TEXT NOT NULL,        -- which source won
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    adj_close NUMERIC,
    volume BIGINT,
    shares_outstanding BIGINT,
    source_versions JSONB,               -- {tase: 'v1.0', eodhd: 'v2.1'}
    reconciliation_status TEXT,          -- 'agreed' | 'mismatch_resolved' | 'mismatch_unresolved'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(company_id, business_date)
);
```

### 4.3 Curated Layer (Bitemporal — The System's Truth)

```sql
-- ============================================================
-- companies (Bitemporal)
-- ============================================================
CREATE TABLE companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name_he TEXT NOT NULL,
    canonical_name_en TEXT,
    primary_isin TEXT,
    primary_ticker_current TEXT,         -- denormalized for convenience
    sector TEXT,                         -- enum from Contract 3.6
    industry_detail TEXT,                -- finer granularity, not used in features
    listing_date DATE,
    delisting_date DATE,                 -- NULL if active
    delisting_reason TEXT,               -- 'merged' | 'taken_private' | 'bankruptcy' | 'voluntary'
    delisting_successor_company_id UUID, -- if merged into another listed company
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- bitemporal columns
    valid_from DATE NOT NULL,
    valid_until DATE,                    -- NULL = current
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ            -- NULL = current record
);

CREATE INDEX idx_companies_active ON companies(company_id) WHERE superseded_at IS NULL;
CREATE INDEX idx_companies_isin ON companies(primary_isin) WHERE superseded_at IS NULL;

-- ============================================================
-- company_tickers_history
-- ============================================================
CREATE TABLE company_tickers_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    ticker TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE,
    reason TEXT,                         -- 'initial' | 'rename' | 'merger' | ...
    source_filing_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ
);

CREATE INDEX idx_tickers_company ON company_tickers_history(company_id);
CREATE INDEX idx_tickers_lookup ON company_tickers_history(ticker, valid_from);

-- ============================================================
-- company_aliases
-- ============================================================
-- For entity resolution: every name variant ever encountered.
CREATE TABLE company_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    alias_text TEXT NOT NULL,
    alias_normalized TEXT NOT NULL,      -- lowercase, no בע"מ, no whitespace
    alias_source TEXT,                   -- 'maya' | 'globes' | 'manual' | ...
    confidence NUMERIC,                  -- 1.0 = manual confirmed, lower = auto-suggested
    valid_from DATE,
    valid_until DATE,
    review_status TEXT,                  -- 'confirmed' | 'auto_suggested' | 'rejected'
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_aliases_normalized ON company_aliases(alias_normalized);
CREATE INDEX idx_aliases_company ON company_aliases(company_id);

-- ============================================================
-- index_membership_history (Bitemporal)
-- ============================================================
-- Critical for sector classification accuracy at as-of dates.
CREATE TABLE index_membership_history (
    membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    index_name TEXT NOT NULL,            -- 'TA-35' | 'TA-90' | 'TA-125' | 'SME-60'
    valid_from DATE NOT NULL,
    valid_until DATE,
    weight NUMERIC,                      -- if available
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ
);

CREATE INDEX idx_idxmem_company ON index_membership_history(company_id, index_name);
CREATE INDEX idx_idxmem_lookup ON index_membership_history(index_name, valid_from, valid_until);

-- ============================================================
-- prices_daily (TimescaleDB Hypertable, Bitemporal)
-- ============================================================
CREATE TABLE prices_daily (
    company_id UUID NOT NULL REFERENCES companies(company_id),
    business_date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC NOT NULL,
    adj_close NUMERIC NOT NULL,
    volume BIGINT,
    shares_outstanding BIGINT,
    market_cap_ils NUMERIC,              -- close * shares_outstanding
    primary_source TEXT NOT NULL,
    source_priority INT NOT NULL,
    ingestion_lineage JSONB NOT NULL,    -- {tase: ingestion_id, eodhd: ingestion_id, ...}
    -- bitemporal
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (company_id, business_date, recorded_at)
);

SELECT create_hypertable('prices_daily', 'business_date', chunk_time_interval => INTERVAL '1 year');

CREATE INDEX idx_prices_active ON prices_daily(company_id, business_date) 
    WHERE superseded_at IS NULL;
CREATE INDEX idx_prices_recorded ON prices_daily(recorded_at);

-- ============================================================
-- corporate_actions (Bitemporal)
-- ============================================================
CREATE TABLE corporate_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    action_type TEXT NOT NULL,           -- 'split' | 'dividend' | 'merger' | 'delisting' | 'rights_issue' | 'spinoff'
    announcement_date DATE,
    ex_date DATE NOT NULL,
    record_date DATE,
    payment_date DATE,
    details JSONB NOT NULL,              -- ratio, amount, currency, terms
    source_filing_id UUID,               -- references staging_filings_parsed
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ
);

CREATE INDEX idx_corpact_company_date ON corporate_actions(company_id, ex_date);
CREATE INDEX idx_corpact_type ON corporate_actions(action_type);

-- ============================================================
-- intraday_quotes_summary (Bitemporal — daily aggregate)
-- ============================================================
-- Daily aggregate of bid-ask spread data.
-- Tick-level data NOT stored (too large; aggregated at ingestion).
-- Source: TASE intraday quotes (paid tier) when available, else synthetic fallback.
CREATE TABLE intraday_quotes_summary (
    company_id UUID NOT NULL REFERENCES companies(company_id),
    business_date DATE NOT NULL,
    avg_bid_ask_spread NUMERIC,           -- absolute spread, ILS
    avg_spread_pct NUMERIC,                -- spread / mid_price
    avg_mid_price NUMERIC,
    primary_source TEXT,                   -- 'tase_intraday' | 'sector_median_fallback' | 'default_fallback'
    sample_count INT,                      -- # observations aggregated (NULL if synthetic)
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE if fallback was applied
    fallback_tier INT,                     -- 1 = sector median, 2 = default 50bps, NULL = real data
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (company_id, business_date, recorded_at)
);

CREATE INDEX idx_intraday_summary_active ON intraday_quotes_summary(company_id, business_date)
    WHERE superseded_at IS NULL;
CREATE INDEX idx_intraday_synthetic ON intraday_quotes_summary(business_date)
    WHERE is_synthetic = TRUE AND superseded_at IS NULL;

-- ============================================================
-- events (THE core table, Bitemporal)
-- ============================================================
CREATE TABLE events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),

    -- TIMING — read carefully, this is the anti-leakage cornerstone
    event_timestamp TIMESTAMPTZ,         -- claimed by source: when did event "happen"
    event_observable_at TIMESTAMPTZ NOT NULL, -- WHEN OUR SYSTEM COULD FIRST SEE IT
    
    -- Classification
    event_type_l1 TEXT NOT NULL,
    event_type_l2 TEXT,
    
    -- Source & lineage
    source_type TEXT NOT NULL,           -- 'filing' | 'news' | 'macro_derived'
    source_record_id UUID,               -- FK to staging table (filings_parsed or news_tagged)
    source_tier INT NOT NULL,            -- 1..4 (Contract §3.4); derived from source_type via fixed lookup;
                                         -- in feature vector named `event_source_tier`
    
    -- Content
    headline_or_title TEXT,
    features JSONB,                      -- extracted: {magnitude, surprise, etc.}
    
    -- Tagging metadata
    tagger_version TEXT NOT NULL,
    tagger_confidence NUMERIC,
    
    -- Quarantine
    is_quarantined BOOLEAN DEFAULT FALSE,
    quarantine_reason TEXT,
    
    -- Bitemporal
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ
);

CREATE INDEX idx_events_company_obs ON events(company_id, event_observable_at) 
    WHERE superseded_at IS NULL AND is_quarantined = FALSE;
CREATE INDEX idx_events_obs_at ON events(event_observable_at) 
    WHERE superseded_at IS NULL;
CREATE INDEX idx_events_type ON events(event_type_l1, event_type_l2);
CREATE INDEX idx_events_tagger ON events(tagger_version);

-- ============================================================
-- macro_daily
-- ============================================================
CREATE TABLE macro_daily (
    series_id TEXT NOT NULL,             -- 'VIX' | 'SP500' | 'USDILS_BOI' | 'BOI_RATE'
    business_date DATE NOT NULL,
    value NUMERIC NOT NULL,
    primary_source TEXT NOT NULL,
    ingestion_lineage JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (series_id, business_date, recorded_at)
);

CREATE INDEX idx_macro_active ON macro_daily(series_id, business_date) 
    WHERE superseded_at IS NULL;

-- ============================================================
-- tase_trading_calendar
-- ============================================================
CREATE TABLE tase_trading_calendar (
    business_date DATE PRIMARY KEY,
    is_trading_day BOOLEAN NOT NULL,
    session_type TEXT,                   -- 'full' | 'half' | 'closed'
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.4 Features Layer

```sql
-- ============================================================
-- features_daily (TimescaleDB Hypertable)
-- ============================================================
-- One row per (company, date, feature_set_version).
-- Forward-looking compatibility: multiple feature_set_versions coexist.
CREATE TABLE features_daily (
    company_id UUID NOT NULL REFERENCES companies(company_id),
    feature_date DATE NOT NULL,
    feature_set_version TEXT NOT NULL,   -- 'v1.0' (matches Contract version)
    features JSONB NOT NULL,             -- {market_cap_log: 9.2, vix_level: 18.5, ...}
    feature_completeness NUMERIC,        -- fraction of non-missing features
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, feature_date, feature_set_version)
);

SELECT create_hypertable('features_daily', 'feature_date', chunk_time_interval => INTERVAL '1 year');

-- ============================================================
-- features_at_event
-- ============================================================
-- Snapshot of feature vector at the time of an event.
-- Critical: one row per event. Used by Decision Model and Memory.
CREATE TABLE features_at_event (
    event_id UUID PRIMARY KEY REFERENCES events(event_id),
    feature_set_version TEXT NOT NULL,
    features JSONB NOT NULL,
    -- Bucketed dimensions for Memory hard filtering (Contract §4.1).
    -- Computed in feature_builder from market_cap_log and liquidity_score.
    market_cap_bucket TEXT NOT NULL,    -- 'large' | 'mid' | 'small'
    liquidity_bucket TEXT NOT NULL,     -- 'large' | 'mid' | 'small'
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- denormalized for query efficiency
    company_id UUID NOT NULL,
    event_observable_at TIMESTAMPTZ NOT NULL,
    CHECK (market_cap_bucket IN ('large', 'mid', 'small')),
    CHECK (liquidity_bucket IN ('large', 'mid', 'small'))
);

CREATE INDEX idx_feat_event_obs ON features_at_event(event_observable_at);
CREATE INDEX idx_feat_event_version ON features_at_event(feature_set_version);
CREATE INDEX idx_feat_event_buckets ON features_at_event(market_cap_bucket, liquidity_bucket);
```

**Required keys in `features_at_event.features` JSONB** (validated at write time via Pydantic):

```
Model features (Contract §3, used by Decision Model):
  event_type_l1            : str                  -- categorical (6)
  event_type_l2            : str | null           -- categorical (~30)
  event_magnitude          : float
  event_source_tier        : int (1..4)           -- ordinal
  market_cap_log           : float
  sector                   : str                  -- categorical (8)
  liquidity_score          : float (0..1)
  vix_level                : float
  ta35_trend               : float
  usdils_5d_change         : float
  recent_return_20d        : float
  volatility_20d           : float

Missing flags (binary 0/1):
  event_magnitude_missing  : 0 | 1

Auxiliary fields (NOT model features; required for cost calc / target / Memory):
  spread_pct               : float (≥ 0)          -- used in cost model and target
  spread_is_synthetic      : 0 | 1                -- 1 if spread came from fallback
  market_cap_ils           : numeric (raw market cap, ILS)
  adv_20                   : numeric (≥ 0)        -- 20-day average daily volume in ILS
```

**Bucket computation** (deterministic, frozen, lives in feature_builder):

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

Thresholds זהים ל-Contract §4.1 ומוקפאים (שינוי = bump version).

### 4.5 Audit & Lineage

```sql
-- ============================================================
-- ingestion_runs
-- ============================================================
-- Every batch/poll job logs a run.
CREATE TABLE ingestion_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name TEXT NOT NULL,              -- 'tase_eod_prices' | 'maya_polling' | ...
    job_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,                -- 'running' | 'success' | 'failed' | 'partial'
    records_fetched INT,
    records_inserted INT,
    records_skipped INT,
    error_summary TEXT,
    metadata JSONB
);

CREATE INDEX idx_runs_job_time ON ingestion_runs(job_name, started_at DESC);
CREATE INDEX idx_runs_status ON ingestion_runs(status, started_at DESC) 
    WHERE status IN ('failed', 'partial');

-- ============================================================
-- data_corrections_log
-- ============================================================
-- Every retroactive correction is logged here. Append-only.
CREATE TABLE data_corrections_log (
    correction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name TEXT NOT NULL,
    record_pk JSONB NOT NULL,            -- {company_id, business_date, ...}
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    correction_type TEXT,                -- 'source_correction' | 'parser_fix' | 'manual_override'
    source_of_correction TEXT,
    detected_at TIMESTAMPTZ NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by TEXT NOT NULL,            -- user / job name
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_corrections_table_time ON data_corrections_log(table_name, applied_at DESC);

-- ============================================================
-- dropped_events_log
-- ============================================================
-- Events that didn't make it into events table.
CREATE TABLE dropped_events_log (
    drop_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID,               -- FK to staging
    drop_reason TEXT NOT NULL,           -- 'missing_required_feature' | 'low_tagger_confidence' | ...
    drop_details JSONB,
    dropped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- quarantine_log
-- ============================================================
CREATE TABLE quarantine_log (
    quarantine_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at TIMESTAMPTZ,
    release_reason TEXT
);

-- ============================================================
-- reconciliation_results
-- ============================================================
CREATE TABLE reconciliation_results (
    recon_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recon_type TEXT NOT NULL,            -- 'price_cross_source' | 'filing_completeness' | ...
    business_date DATE,
    run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_compared INT,
    mismatches INT,
    auto_resolved INT,
    manual_review_required INT,
    details JSONB
);
```

### 4.6 Decision Layer Tables

טבלאות אלה owned לוגית by Decision Model layer, אבל ה-DDL מתועד פה כדי שכל הschema יהיה במקום אחד. ההגדרה ב-DECISION_MODEL_SPEC §8.4 מתייחסת לטבלה זו.

```sql
-- ============================================================
-- decisions_log
-- ============================================================
-- One row per decision (take or skip) made by the system.
-- Append-only. Decisions are NEVER updated retroactively.
CREATE TABLE decisions_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(event_id),
    decision TEXT NOT NULL,                    -- 'take' | 'skip'
    reason TEXT NOT NULL,                      -- e.g. 'p=0.62, threshold=0.55' | 'ci_crosses_threshold'
    p_point NUMERIC NOT NULL,
    p_lower_p10 NUMERIC NOT NULL,
    p_upper_p90 NUMERIC NOT NULL,
    threshold_applied NUMERIC NOT NULL,
    memory_flags TEXT[],
    model_version TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (decision IN ('take', 'skip')),
    CHECK (p_lower_p10 <= p_point AND p_point <= p_upper_p90)
);

CREATE INDEX idx_decisions_event ON decisions_log(event_id);
CREATE INDEX idx_decisions_time ON decisions_log(decided_at DESC);
CREATE INDEX idx_decisions_model_version ON decisions_log(model_version);

-- ============================================================
-- model_deployments
-- ============================================================
-- Track which model version was active when.
-- Bitemporal-style: superseded_at NULL = currently active.
CREATE TABLE model_deployments (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version TEXT NOT NULL,               -- e.g. '1.0.3' (per Decision Model §13.1)
    deployed_at TIMESTAMPTZ NOT NULL,
    deployed_by TEXT NOT NULL,                 -- user id / system user
    deployment_metadata JSONB,                 -- gates passed, signoff details, code git_sha, etc.
    superseded_at TIMESTAMPTZ,                 -- NULL = still active
    rollback_reason TEXT                       -- non-NULL only if superseded due to rollback
);

CREATE UNIQUE INDEX idx_model_active 
    ON model_deployments(model_version) 
    WHERE superseded_at IS NULL;
CREATE INDEX idx_model_deployed_at ON model_deployments(deployed_at DESC);

-- ============================================================
-- paper_trading_results
-- ============================================================
-- Outcomes of decisions in paper trading.
-- One row per executed (paper) trade. Skips are NOT recorded here (only in decisions_log).
CREATE TABLE paper_trading_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES decisions_log(decision_id),
    entry_date DATE NOT NULL,
    entry_price NUMERIC NOT NULL,              -- paper fill assumption (close at t-1)
    entry_spread_pct NUMERIC,                  -- spread at entry (for cost calc)
    exit_date DATE,                            -- NULL while open
    exit_price NUMERIC,
    exit_spread_pct NUMERIC,
    raw_return NUMERIC,                        -- (exit_price - entry_price) / entry_price
    net_return_after_costs NUMERIC,            -- raw_return - total_costs
    holding_days INT,
    closed_reason TEXT,                        -- 'horizon_reached' | 'manual_exit' | 'soft_kill' | 'delisting'
    user_confirmed BOOLEAN NOT NULL,           -- per Contract §7.8 (must be TRUE)
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    UNIQUE(decision_id)                        -- one open paper position per decision
);

CREATE INDEX idx_papertrading_decision ON paper_trading_results(decision_id);
CREATE INDEX idx_papertrading_open ON paper_trading_results(entry_date) 
    WHERE exit_date IS NULL;
CREATE INDEX idx_papertrading_closed ON paper_trading_results(closed_at DESC) 
    WHERE exit_date IS NOT NULL;
```

---

## 5. Bitemporal Design

### 5.1 שני צירי הזמן

```
┌────────────────────────────────────────────────────────────┐
│  TRANSACTION TIME (recorded_at / superseded_at):           │
│  מתי כתבנו את הrecord למסד.                                 │
│                                                            │
│  recorded_at: כשהrecord נוצר.                              │
│  superseded_at: כשrecord חדש החליף אותו (NULL = עכשיו).    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  VALID TIME (valid_from / valid_until):                    │
│  מתי הfact היה נכון בעולם.                                  │
│                                                            │
│  valid_from: כשהfact התחיל להיות נכון.                      │
│  valid_until: כשהfact הפסיק להיות נכון (NULL = עדיין נכון). │
└────────────────────────────────────────────────────────────┘
```

**Records לא מתעדכנים — מוחלפים.** עדכון = `UPDATE old SET superseded_at = now()` + `INSERT new RECORD`.

### 5.2 מתי משתמשים ב-bitemporal

| Table | Bitemporal? | למה |
|---|---|---|
| `companies` | ✓ | sector מתעדכן, name משתנה |
| `company_tickers_history` | ✓ | ticker משתנה |
| `index_membership_history` | ✓ | חברות נכנסות/יוצאות מ-TA-35 |
| `prices_daily` | ✓ (transaction time בלבד) | corrections retroactive |
| `corporate_actions` | ✓ | dividends מתוקנים לפעמים |
| `events` | ✓ | re-tagging עם parser חדש |
| `macro_daily` | ✓ (transaction time) | revisions של macro data |
| `staging_*` | ✗ | versioned by parser_version |
| `raw_*` | ✗ | append-only, immutable |
| `features_daily` | ✗ | versioned by feature_set_version |

### 5.3 As-Of Queries — דפוסים קנוניים

**שאלה:** מה היה מחיר המניה X ב-2024-03-15, **כפי שהיה ידוע ב-2024-03-15 בסוף יום**?

```sql
SELECT close, adj_close, volume
FROM prices_daily
WHERE company_id = :company_id
  AND business_date = '2024-03-15'
  AND recorded_at <= '2024-03-15 23:59:59 UTC'
  AND (superseded_at IS NULL OR superseded_at > '2024-03-15 23:59:59 UTC')
ORDER BY recorded_at DESC
LIMIT 1;
```

**שאלה:** מה היה ידוע על company X ב-תאריך as_of?

```sql
SELECT *
FROM companies
WHERE company_id = :company_id
  AND valid_from <= :as_of_date
  AND (valid_until IS NULL OR valid_until > :as_of_date)
  AND recorded_at <= :as_of_timestamp
  AND (superseded_at IS NULL OR superseded_at > :as_of_timestamp)
ORDER BY recorded_at DESC
LIMIT 1;
```

**שאלה:** events relevant לbacktest עד תאריך X (אנטי-leakage):

```sql
SELECT *
FROM events
WHERE event_observable_at <= :as_of_timestamp
  AND recorded_at <= :as_of_timestamp
  AND (superseded_at IS NULL OR superseded_at > :as_of_timestamp)
  AND is_quarantined = FALSE;
```

### 5.4 Helper Functions — חובה לעטוף

**אסור** לקוד אפליקטיבי לכתוב את ה-bitemporal filters ידנית. סיכון לטעות. עוטפים בfunctions קנוניות. ה-application code משתמש **רק** ב-functions אלה. קוד שעוקף = code review reject.

```sql
-- ============================================================
-- prices_daily_as_of
-- ============================================================
CREATE OR REPLACE FUNCTION prices_daily_as_of(p_as_of TIMESTAMPTZ)
RETURNS TABLE (
    company_id UUID,
    business_date DATE,
    close NUMERIC,
    adj_close NUMERIC,
    volume BIGINT,
    market_cap_ils NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT DISTINCT ON (company_id, business_date)
        company_id, business_date, close, adj_close, volume, market_cap_ils
    FROM prices_daily
    WHERE recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
    ORDER BY company_id, business_date, recorded_at DESC;
$$;

-- ============================================================
-- events_as_of
-- ============================================================
-- Returns events that were observable AND recorded before p_as_of,
-- excluding quarantined and superseded.
CREATE OR REPLACE FUNCTION events_as_of(
    p_window_start TIMESTAMPTZ,
    p_window_end TIMESTAMPTZ,
    p_as_of TIMESTAMPTZ
)
RETURNS SETOF events LANGUAGE SQL STABLE AS $$
    SELECT DISTINCT ON (event_id) *
    FROM events
    WHERE event_observable_at >= p_window_start
      AND event_observable_at <= p_window_end
      AND event_observable_at <= p_as_of   -- can't see future events
      AND recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
      AND is_quarantined = FALSE
    ORDER BY event_id, recorded_at DESC;
$$;

-- ============================================================
-- features_at_event_as_of
-- ============================================================
CREATE OR REPLACE FUNCTION features_at_event_as_of(
    p_event_ids UUID[],
    p_feature_set_version TEXT,
    p_as_of TIMESTAMPTZ
)
RETURNS SETOF features_at_event LANGUAGE SQL STABLE AS $$
    SELECT *
    FROM features_at_event
    WHERE event_id = ANY(p_event_ids)
      AND feature_set_version = p_feature_set_version
      AND computed_at <= p_as_of;
$$;

-- ============================================================
-- companies_as_of
-- ============================================================
CREATE OR REPLACE FUNCTION companies_as_of(p_as_of TIMESTAMPTZ)
RETURNS SETOF companies LANGUAGE SQL STABLE AS $$
    SELECT DISTINCT ON (company_id) *
    FROM companies
    WHERE valid_from <= p_as_of::date
      AND (valid_until IS NULL OR valid_until > p_as_of::date)
      AND recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
    ORDER BY company_id, recorded_at DESC;
$$;

-- ============================================================
-- macro_daily_as_of
-- ============================================================
CREATE OR REPLACE FUNCTION macro_daily_as_of(p_as_of TIMESTAMPTZ)
RETURNS TABLE (
    series_id TEXT,
    business_date DATE,
    value NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT DISTINCT ON (series_id, business_date)
        series_id, business_date, value
    FROM macro_daily
    WHERE recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
    ORDER BY series_id, business_date, recorded_at DESC;
$$;

-- ============================================================
-- intraday_quotes_summary_as_of
-- ============================================================
CREATE OR REPLACE FUNCTION intraday_quotes_summary_as_of(p_as_of TIMESTAMPTZ)
RETURNS TABLE (
    company_id UUID,
    business_date DATE,
    avg_spread_pct NUMERIC,
    is_synthetic BOOLEAN
) LANGUAGE SQL STABLE AS $$
    SELECT DISTINCT ON (company_id, business_date)
        company_id, business_date, avg_spread_pct, is_synthetic
    FROM intraday_quotes_summary
    WHERE recorded_at <= p_as_of
      AND (superseded_at IS NULL OR superseded_at > p_as_of)
    ORDER BY company_id, business_date, recorded_at DESC;
$$;

-- ============================================================
-- is_trading_day (used for embargo computation in Decision Model)
-- ============================================================
CREATE OR REPLACE FUNCTION is_trading_day(p_date DATE)
RETURNS BOOLEAN LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(
        (SELECT is_trading_day FROM tase_trading_calendar WHERE business_date = p_date),
        FALSE
    );
$$;

-- ============================================================
-- subtract_trading_days (Decision Model embargo helper)
-- ============================================================
CREATE OR REPLACE FUNCTION subtract_trading_days(
    p_end_date DATE,
    p_n_trading_days INT
)
RETURNS DATE LANGUAGE plpgsql STABLE AS $$
DECLARE
    cursor_date DATE := p_end_date;
    days_subtracted INT := 0;
BEGIN
    WHILE days_subtracted < p_n_trading_days LOOP
        cursor_date := cursor_date - INTERVAL '1 day';
        IF is_trading_day(cursor_date) THEN
            days_subtracted := days_subtracted + 1;
        END IF;
    END LOOP;
    RETURN cursor_date;
END;
$$;

-- ============================================================
-- add_trading_days (symmetric — for embargo end computation)
-- ============================================================
CREATE OR REPLACE FUNCTION add_trading_days(
    p_start_date DATE,
    p_n_trading_days INT
)
RETURNS DATE LANGUAGE plpgsql STABLE AS $$
DECLARE
    cursor_date DATE := p_start_date;
    days_added INT := 0;
BEGIN
    WHILE days_added < p_n_trading_days LOOP
        cursor_date := cursor_date + INTERVAL '1 day';
        IF is_trading_day(cursor_date) THEN
            days_added := days_added + 1;
        END IF;
    END LOOP;
    RETURN cursor_date;
END;
$$;
```

### 5.5 Replay Capability

לכל backtest — capture של:
```
{
  "as_of_timestamp": "2024-03-15T17:00:00Z",
  "feature_set_version": "v1.0",
  "tagger_version": "v1.0",
  "parser_versions": {"maya": "v1.0", "magna": "v1.0"},
  "model_version": "v1.0"
}
```

ריצה מחדש עם אותם versions → אותה תוצאה (deterministic). אם תוצאה משתנה → bug.

---

## 6. Entity Resolution

### 6.1 העיקרון

חברה אחת ב-עולם = `company_id` אחד בDB, **לעד**. גם אם:
- שינתה שם (חתת סוכר → סטראוס).
- שינתה ticker.
- התמזגה (קלאל ביוטכנולוגיה → טבע) — *אך רק אם הCorporate identity המשיכה*.
- נמחקה ואז נרשמה מחדש (נדיר מאוד).

מיזוג של שתי חברות נפרדות → company_id חדש לישות הממוזגת + שמירה על שתי הisuhios הקודמות.

### 6.2 Canonical Identity

`company_id` אחד מקושר ל-**ISIN** primary. ISIN הוא ה-anchor הכי יציב.
- אם ISIN משתנה (rare) → bitemporal record חדש עם רישום ב-data_corrections_log.

### 6.3 Resolution Cascade

כשמגיע alias חדש (ממקור כלשהו), נסיון resolution:

**Layer 1 — Deterministic:**
1. ISIN match → unique match → done.
2. Active ticker match (ב-`company_tickers_history` עם valid_from/until) → done.
3. Exact name match על `company_aliases.alias_normalized` (confidence ≥ 0.9) → done.

**Layer 2 — Fuzzy (auto-suggest, requires review):**
4. Levenshtein distance ≤ 3 על normalized name → suggestion עם `confidence = 0.5-0.8`.
5. Substring match (חלק מהשם, e.g., "טבע" → "טבע תעשיות פרמצבטיות") → suggestion עם `confidence = 0.3-0.6`.

**Layer 3 — Manual:**
6. אם אף אחד לא מתאים → quarantine. סנכרון ידני.

### 6.4 Normalization של שמות לפני match

```python
def normalize_company_name(name: str) -> str:
    name = name.lower().strip()
    # Remove corporate suffixes
    for suffix in ['בע"מ', "בע'מ", 'בעמ', 'ltd.', 'ltd', 'inc.', 'inc', 'corp.', 'corp']:
        name = name.replace(suffix, '')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove punctuation that varies
    name = re.sub(r'["\'`.,]', '', name)
    return name
```

Frozen function. Changes = bump major version.

### 6.5 Manual Review Workflow

טבלה: `company_aliases` עם `review_status`.

**יומי:**
1. Job `entity_resolution_review` מוציא כל `auto_suggested` מהיממה.
2. CLI tool מציג למפתח: "Globes כותב 'טבע פרמצבטיקה'. Auto-match: 'טבע תעשיות פרמצבטיות' (confidence 0.78). Confirm/Reject/Manual?"
3. אישור → `review_status = 'confirmed'`, מעבר ל-Layer 1 בעתיד.
4. דחייה → record חדש או נחשב לחברה שונה.

ב-MVP: 30-60 דק' שבועיות. אחרי 3 חודשים: 10-15 דק'/שבוע.

### 6.6 Mergers & Acquisitions Handling

**מקרה 1: חברה A נרכשה במלואה ע"י B, A מפסיקה להיסחר.**
- `companies.delisting_date` של A מתמלא.
- `companies.delisting_reason = 'merged'`.
- `companies.delisting_successor_company_id = B.company_id`.
- אירועים היסטוריים של A נשמרים תחת A.company_id (לא ממופים מחדש).

**מקרה 2: שתי חברות מתמזגות לישות חדשה C.**
- C מקבל `company_id` חדש.
- A ו-B מקבלות `delisting_date`, `delisting_successor_company_id = C.company_id`.
- אירועים היסטוריים של A ושל B **לא** מועברים ל-C. הם נשארים תחת A ו-B.

**מקרה 3: Spinoff (חברה D מתפצלת מ-E).**
- D מקבל `company_id` חדש, `listing_date = spinoff_date`.
- E ממשיכה תחת אותו `company_id`.
- אירוע ה-spinoff נרשם ב-`corporate_actions` תחת E.

**Critical:** אירועים היסטוריים **לא נודדים** בין companies בעקבות M&A. זה מתאים ל-statistical reality — חברה שונה = sample נפרד.

### 6.7 Delisting Tracking

`delisting_date` חייב להיות מדויק (ליום). ועוקבים בkpi:
- `% of historical TA-100 members delisted` — proxy ל-survivorship coverage.
- אם < 15% מהדגימות הן delisted → דאטה לא שלם.

---

## 7. Ingestion Architecture

### 7.1 Job Schedule (Frozen ב-V1)

| Job | Frequency | Window | Type |
|---|---|---|---|
| `tase_eod_prices` | Daily, 19:00 IST | After market close | batch |
| `tase_eod_prices_adjustment` | Daily, 22:00 IST | Post-settlement | batch |
| `eodhd_eod_prices` (fallback) | Daily, 23:00 IST | Cross-validate | batch |
| `maya_polling` | Every 30 min | 09:00-17:30 IST trading days | poll |
| `maya_polling_offhours` | Every 2 hours | All other times | poll |
| `magna_polling` | Every 2 hours | 24/7 | poll |
| `news_rss` | Every 15 min | 24/7 | poll |
| `fred_macro` | Daily, 23:00 IST | EOD update | batch |
| `boi_data` | Daily, 18:30 IST | After BoI publication | batch |
| `corporate_actions_check` | Daily, 06:00 IST | Apply ex-date adjustments | batch |
| `entity_resolution_review` | Daily, 07:00 IST | Human review queue prep | batch |
| `reconciliation_prices` | Daily, 23:30 IST | Cross-source check | batch |
| `parser_run` | Hourly | Process new raw_filings | batch |
| `tagger_run` | Hourly | Process new raw_news + parsed filings | batch |
| `feature_builder` | Daily, 04:00 IST (next day) | Build features for previous trading day | batch |

**Time zone:** all schedules in IST. Storage in UTC. Conversion at query time.

### 7.2 Idempotency

**כל job חייב להיות idempotent:** ריצה פעמיים → אותה תוצאה.

מנגנון:
- Raw inserts: `UNIQUE(source, ..., payload_hash)` — duplicate insert = no-op.
- Parser/Tagger: `UNIQUE(ingestion_id, parser_version)` — re-run safe.
- Curated: bitemporal write only if values changed.

**Test:** prefect job for each ingestion script → run twice → verify identical row counts.

### 7.3 Retries & Backoff

| Failure Type | Retry Policy |
|---|---|
| Network timeout (5xx, connection error) | Exponential backoff: 1s, 5s, 30s, 5m, 30m. Max 5 attempts. |
| Auth failure (401/403) | No retry. Alert immediately. |
| Rate limit (429) | Respect `Retry-After` header. Else exponential. |
| Schema error (parse fails) | No retry. Quarantine. Alert. |
| Source returns empty | One retry after 30 min. Then mark `partial` and continue. |

### 7.4 Quarantine Process

Records ש-fail validation:
1. ב-raw layer: written anyway (raw הוא immutable evidence).
2. ב-staging: written with `parse_warnings`, but `tagger_run` skip.
3. ב-curated/events: **not written**, logged in `quarantine_log` instead.

Daily review of quarantine: 5-15 dec/day after MVP stabilizes.

### 7.5 Backfill Strategy

תרחיש: מקור חדש; או חדשנות ב-parser; צריך re-process היסטוריה.

**Procedure:**
1. Run parser/tagger מחדש על raw_* עם version חדש (parallel records ב-staging).
2. ריצת curator מ-staging → curated עם bitemporal (records חדשים, ישנים לא נמחקים).
3. Run validation על השווה תוצאה ישנה לחדשה.
4. אם שינויים major → אמן feature_set_version חדש, refit Decision Model, restart validation per Contract.

Backfill **לא** משכתב history. הוא מוסיף שכבה.

### 7.6 Event-Driven Components (Limited Scope ב-V1)

ה-MVP הוא mostly batch. exception:

- **News RSS poller** רץ ברקע, push events ל-tagger queue (אין צורך באmongodb/queue mechanism — pg_notify מספיק).
- **Filings poller** דומה.

מעבר ל-streaming proper (Kafka/Redpanda) **לא מתבצע ב-V1**. אם בעתיד נדרש intraday → V2 design.

### 7.7 Job Dependencies (DAG)

```
                    raw_price_snapshots
                            ↓
                  staging_prices_normalized
                            ↓
                       prices_daily
                            ↓
                            ├─→ corporate_actions (joins)
                            ↓
                     features_daily ←─── macro_daily
                            ↓
                     features_at_event
                            ↓
                      Decision Model

raw_filings → staging_filings_parsed ─┐
                                      ├─→ events ─→ features_at_event
raw_news → staging_news_tagged ───────┘
```

**Critical:** `feature_builder` חייב להמתין ל-`tase_eod_prices` + `corporate_actions_check` + `fred_macro` + `boi_data`. Prefect handles via `wait_for`.

---

## 8. Anti-Leakage Rules (חוקתי — לא ניתן לשינוי ב-V1.x)

### 8.1 העיקרון: מה ידעתי ב-time T?

לכל החלטה ב-time T, **מותר** להשתמש רק ב-data שהיה ב-DB עם:
- `recorded_at <= T`
- `superseded_at IS NULL OR superseded_at > T`
- (לbitemporal valid time:) `valid_from <= T AND (valid_until IS NULL OR valid_until > T)`

### 8.2 Event Observability — הקריטי ביותר

`event_observable_at` נקבע לפי המקור:

| Source Type | event_observable_at = |
|---|---|
| MAYA filing | `MAX(filing_published_at_tase, raw_filings.fetched_at)` |
| MAGNA filing | `MAX(filing_published_at_isa, raw_filings.fetched_at)` |
| News RSS | `raw_news.fetched_at` (לא `publisher_claimed_at`) |
| Macro update | `business_date + 23:00 UTC` (assuming end-of-day publication) |

**הסיבה ל-MAX:** אם מקור דיווח ב-15:00 אבל הסקרייפר שלנו מצא ב-15:08 — אנחנו ידענו רק ב-15:08. ה-MAX לוכד את ה-late between two timestamps.

**Critical:** `publisher_claimed_at` בחדשות לא נחשב כי headlines נערכות retroactively. הזמן שלנו (`fetched_at`) הוא ground truth.

### 8.3 Same-Day Pricing Rules

**אסור** להשתמש ב-`close` של היום שבו אירוע התרחש כ-feature לאותו אירוע.

```sql
-- WRONG: same-day close
SELECT p.close
FROM events e
JOIN prices_daily p ON p.business_date = DATE(e.event_observable_at)
WHERE p.company_id = e.company_id;

-- RIGHT: previous trading day close
SELECT p.close
FROM events e
JOIN prices_daily p ON p.business_date = (
    SELECT MAX(business_date) FROM tase_trading_calendar
    WHERE business_date < DATE(e.event_observable_at)
      AND is_trading_day = TRUE
)
WHERE p.company_id = e.company_id;
```

(החריג: אם `event_observable_at` הוא לאחר 17:30 IST = post-close, ניתן להשתמש ב-same-day close. אבל זה case-by-case וצריך לעבור automated check.)

### 8.4 Test Set Sanctity

ה-test window לא נראה במהלך פיתוח. נאכף ע"י:
- `test_window_views.log` — record של כל query על test data.
- אם developer מריץ query על test → log entry עם reason.
- אזהרה אוטומטית אם test window נסקר יותר מ-3 פעמים בvalidation cycle.

### 8.5 Random Label Test (חובה לפני כל deployment)

לפני promotion של model חדש:

```python
# Shuffle labels, retrain
shuffled_labels = np.random.permutation(y_train)
model_random = train_decision_model(X_train, shuffled_labels, ...)
auc_random = evaluate(model_random, X_validation, y_validation_shuffled_consistently)

assert auc_random < 0.55, "Leakage detected: model achieves edge on random labels"
```

ריצה זו חובה בכל refit. כל failure → מודל לא promotion.

### 8.6 Forbidden Patterns

חוקים שב-application code אסור לעבור עליהם (CI checks):

- ❌ `WHERE business_date = DATE(:event_time)` — same-day reference.
- ❌ `MAX(value) OVER (...)` בלי PARTITION BY עם temporal bounds — easy leakage.
- ❌ Feature computation על window שכולל את `event_observable_at`.
- ❌ Direct queries על raw/curated tables ללא מעבר דרך as-of view.
- ❌ Tagger שמקבל features אחרי `event_observable_at`.

---

## 9. Validation & Reconciliation

### 9.1 Schema Validation (entry to raw)

לפני כל insert ל-raw_*:

```python
# Pydantic schema for raw_price_snapshot
class RawPricePayload(BaseModel):
    business_date: date
    close: Decimal = Field(gt=0)
    open: Optional[Decimal] = Field(gt=0)
    high: Optional[Decimal] = Field(gt=0)
    low: Optional[Decimal] = Field(gt=0)
    volume: Optional[int] = Field(ge=0)
    
    @validator('high')
    def high_geq_close(cls, v, values):
        if v is not None and 'close' in values and v < values['close']:
            raise ValueError('high < close')
        return v
```

Failure → quarantine, alert. Raw record itself **is still saved** (immutability), but flagged.

### 9.2 Sanity Checks (staging → curated)

```sql
-- Daily price change > 50% without corporate action
SELECT p.company_id, p.business_date, p.close
FROM prices_daily p
JOIN prices_daily p_prev ON p_prev.company_id = p.company_id 
    AND p_prev.business_date = (last trading day before p.business_date)
LEFT JOIN corporate_actions ca ON ca.company_id = p.company_id 
    AND ca.ex_date = p.business_date
WHERE ABS(p.close - p_prev.close) / p_prev.close > 0.5
  AND ca.action_id IS NULL
  AND p.recorded_at >= now() - INTERVAL '1 day';
```

Output → flag לreview. Not auto-rejection (true price spikes happen).

### 9.3 Cross-Source Reconciliation (Daily)

```sql
-- Compare prices across sources for the same (company, date)
WITH source_prices AS (
    SELECT 
        company_id,
        business_date,
        primary_source,
        close
    FROM staging_prices_normalized
    WHERE business_date = :recon_date
)
SELECT 
    company_id,
    business_date,
    MAX(close) - MIN(close) as price_range,
    MAX(close) - MIN(close) / MIN(close) as pct_range,
    array_agg(DISTINCT primary_source) as sources
FROM source_prices
GROUP BY company_id, business_date
HAVING MAX(close) - MIN(close) > GREATEST(MIN(close) * 0.005, 0.01);
```

`> 0.5%` mismatch or > 0.01 absolute (whichever larger) → reconciliation_results entry.

**Resolution policy:**
| Severity | Action |
|---|---|
| 0.5%-2% | Auto-resolve: prefer TASE > EODHD > Yahoo. Log. |
| 2%-10% | Manual review queue. Daily. |
| > 10% | Quarantine the (company, date) record, freeze decisions for that company until resolved. |

### 9.4 Completeness Checks (Daily)

```sql
-- Every active company should have a price for every trading day
WITH expected AS (
    SELECT 
        c.company_id,
        cal.business_date
    FROM companies c
    CROSS JOIN tase_trading_calendar cal
    WHERE cal.is_trading_day = TRUE
      AND cal.business_date BETWEEN c.listing_date AND COALESCE(c.delisting_date, current_date)
      AND c.superseded_at IS NULL
),
actual AS (
    SELECT company_id, business_date
    FROM prices_daily
    WHERE superseded_at IS NULL
)
SELECT 
    e.company_id, 
    e.business_date,
    'MISSING_PRICE' as gap_type
FROM expected e
LEFT JOIN actual a USING (company_id, business_date)
WHERE a.business_date IS NULL;
```

**Threshold:** `< 0.5% missing days` per company per quarter. Above → escalate.

### 9.5 Anomaly Detection

Daily run:
- Z-score > 5 on volume → flag (could be real but worth checking).
- Z-score > 5 on |daily return| → flag (filter for unannounced corp actions).
- Stocks with volume = 0 for 5+ consecutive days → likely halted, validate against TASE.
- `liquidity_score` drop > 0.3 in single day → flag.

### 9.6 Corporate Actions Validation

לכל split/dividend ב-`corporate_actions`:
- Verify `adj_close` ratio matches expected ratio across ex_date.
- If mismatch → quarantine the action + alert.

```python
# Expected adj_close behavior
# For 2:1 split: adj_close BEFORE ex_date should be HALF of raw close
expected_ratio = 0.5 if split_ratio == "2:1" else ...
actual_ratio = adj_close_before_ex / close_before_ex
assert abs(actual_ratio - expected_ratio) < 0.02, "Adjustment mismatch"
```

### 9.7 Data Quality Dashboard

Grafana panels (refresh hourly):

1. **Freshness:** time since last successful run, per source.
2. **Completeness:** % of expected (company, date) combinations present.
3. **Reconciliation rate:** % matching across sources.
4. **Quarantine queue depth:** pending items.
5. **Failed runs (24h):** count + drill-down.
6. **Parser confidence distribution:** histogram of `parse_confidence`.
7. **Tagger confidence distribution:** histogram of `tagger_confidence`.
8. **Entity resolution backlog:** auto-suggested awaiting review.
9. **Bitemporal correction rate:** count of `data_corrections_log` entries per day.

Daily morning review: ~5 דק'.

---

## 10. Recovery Scenarios

### 10.1 Source Down (Single Day)

**Scenario:** TASE API לא זמין יום שלם.

**Detection:** `ingestion_runs` עם `status = 'failed'` + retry exhausted.

**Action:**
1. Activate fallback source (EODHD).
2. Mark `prices_daily.primary_source = 'eodhd'` for that day, log.
3. When TASE back up:
   - Fetch missing day.
   - Run reconciliation against EODHD.
   - If match → supersede EODHD record with TASE record (preserve ingestion lineage in JSONB).
   - If mismatch → manual review.

### 10.2 Source Down (Multi-Day)

**Scenario:** TASE API down 3+ days.

**Action:**
1. Continue with fallback.
2. Alert escalation. This is a vendor issue.
3. **Do not** make trading decisions during the gap if reconciliation rate falls < 95%.

### 10.3 Parser Bug

**Scenario:** Bug in MAYA parser misclassifies hundreds of filings.

**Action:**
1. Deploy fix as `parser_version: v1.1`.
2. Run `staging_filings_parsed` insertion for affected `raw_filings.ingestion_id` with new version (parallel records).
3. Update curator to prefer latest parser_version.
4. New events created with bitemporal supersede of old.
5. **Do not delete old `events` records.** They represent "what we believed at time X."
6. Backtest implications: any model trained on old events must be retrained.

### 10.4 Wrong Entity Mapping

**Scenario:** Discovered that "טבע" headline was mapped to wrong company_id.

**Action:**
1. Add correct alias to `company_aliases`.
2. Identify all events with wrong mapping (query staging_news_tagged with old alias).
3. Re-run tagger on affected raw_news.
4. Bitemporal supersede on `events`.
5. Log entries in `data_corrections_log`.

### 10.5 Missing Day (Historical Gap Found)

**Scenario:** Notice that 2019-04-12 has no prices for 30 companies, was a partial trading day (chag).

**Action:**
1. Verify with `tase_trading_calendar`. If indeed half-day with limited trading → expected behavior, no action.
2. If full trading day → backfill from secondary source.
3. If neither → flag in `tase_trading_calendar`, no fill needed.

### 10.6 Retroactive Correction (Source Republishes)

**Scenario:** TASE issues correction for adj_close 2 weeks back due to dividend reclassification.

**Action:**
1. New `raw_price_snapshots` record (UNIQUE allows because hash differs).
2. New record in `prices_daily` with `recorded_at = now()`.
3. Old record auto-superseded.
4. Log entry in `data_corrections_log`.
5. **Do not** rerun backtests automatically. Backtests use as-of queries; the correction won't affect a backtest with `as_of_timestamp` < correction time. But for new backtests, the correction is now visible.

### 10.7 Database Corruption / Disk Failure

**Scenario:** Disk failure on PostgreSQL.

**RPO:** 5 minutes (WAL archiving).
**RTO:** 2 hours (restore from snapshot + WAL replay).

**Procedure:**
1. Provision new instance.
2. Restore from latest pg_basebackup.
3. WAL replay to last available WAL.
4. Verify: count of records per major table, latest `recorded_at`.
5. Re-run any ingestion jobs whose run records are missing/incomplete.

**Drill quarterly.** Document RTO actually achieved.

### 10.8 Backup Verification

**Monthly:** restore latest backup to staging environment, run full schema validation. If fails → backups are not trustworthy → fix immediately.

---

## 11. Storage & Retention

### 11.1 Hot vs Cold

| Data | Storage | Retention |
|---|---|---|
| Raw blobs (PDFs) | FS / S3 | 5 years hot, then S3 IA |
| Raw tables (DB) | PostgreSQL | Forever |
| Staging tables | PostgreSQL | 2 years hot, then archive |
| Curated tables | PostgreSQL | Forever |
| Features tables | PostgreSQL, compressed | 5 years hot, then archive |
| Audit logs | PostgreSQL | 3 years hot, then export |
| WAL archives | S3 / Backblaze | 30 days |

### 11.2 Compression

TimescaleDB native compression:

```sql
ALTER TABLE prices_daily SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'business_date DESC',
    timescaledb.compress_segmentby = 'company_id'
);

SELECT add_compression_policy('prices_daily', INTERVAL '90 days');
```

Same for `features_daily`, `macro_daily`.

### 11.3 Backups

- **Daily:** `pg_dump` of full DB → local + Backblaze.
- **Hourly:** WAL archives → Backblaze.
- **Weekly:** `pg_basebackup` for fast restore base.

**Cost estimate:** ~$10-15/month for backup storage at MVP scale.

---

## 12. Performance Budgets

| Operation | Target |
|---|---|
| `prices_daily_as_of()` for single company | < 50ms |
| Memory pool query (after hard filters) | < 200ms |
| Daily feature build (full universe) | < 5 min |
| Daily ingestion (all sources) | < 30 min |
| Daily reconciliation | < 2 min |
| Backtest (5 years, full universe) | < 30 min |

If any breaks → `data_quality_dashboard` alerts → investigate before adding features.

---

## 13. Compliance & Privacy

(Brief; deeper review separate.)

- **Data sources licensing:** TASE Data Hub paid plan covers internal/research use. RSS = public domain. Re-distribution forbidden.
- **No PII collected:** system stores no individual user data.
- **No third-party access:** per Contract 7.10.
- **Audit trail:** `data_corrections_log` + `ingestion_runs` provide full lineage if ever needed for compliance review.

---

## 14. Implementation Roadmap

| Week | Deliverable |
|---|---|
| 1-2 | Postgres + TimescaleDB stack. Schema migrations (Alembic). Empty tables, indices. |
| 3-4 | TASE EOD prices ingestion + EODHD fallback. Companies + entity resolution v1. |
| 5-6 | MAYA scraper + raw_filings storage. PDF blob handling. |
| 7-8 | First MAYA parser (earnings, guidance). staging_filings_parsed populated. |
| 9 | Macro ingestion (FRED + BoI). News RSS poller. |
| 10 | bitemporal infrastructure: as-of views, helper functions. |
| 11 | Reconciliation jobs. Data quality dashboard. |
| 12 | corporate_actions handling + adjustment validation. |
| 13-14 | features_daily + features_at_event computation pipeline. |
| 15-16 | End-to-end test: events table populated, features at event computed, as-of query verified. |
| 17 | Backup procedure + recovery drill. |
| 18 | Documentation + handoff to Decision Model phase. |

**At week 18:** the Data Layer is ready for `DECISION_MODEL_SPEC_V1.md` phase.

---

## 15. Glossary

| Term | Definition |
|---|---|
| **Raw layer** | Immutable storage of source data exactly as received |
| **Staging layer** | Versioned transformations of raw (parsed, tagged) |
| **Curated layer** | Bitemporal source-of-truth tables (companies, events, prices) |
| **Bitemporal** | Tracking both valid time (when fact was true in world) and transaction time (when recorded) |
| **As-of query** | Query reconstructing system state at a specific past time |
| **Quarantine** | Record that failed validation; saved but unused by downstream |
| **Backfill** | Re-processing raw data with new parser/tagger version |
| **Reconciliation** | Cross-source comparison to detect mismatches |
| **Idempotent** | Operation with same result regardless of repetition |
| **Lineage** | Trace of which raw records produced a curated value |
| **Survivorship bias** | Excluding delisted entities from history (forbidden here) |
| **Look-ahead bias** | Using information not available at decision time (forbidden here) |
| **Embargo** | Time gap between train and test windows preventing leakage |

---

## 16. Signatures

```
Owner:        ____________________   Date: __________
Version:      V1.0.1
Companion to: TECHNICAL_CONTRACT_V1.0.1.md
Document hash (SHA-256): __________________________________
Repo location: DATA_LAYER_SPEC_V1.0.1.md
Amendments applied: AMENDMENT_V1.0.1.md
```

---

**END OF DATA LAYER SPECIFICATION V1.0.1**
