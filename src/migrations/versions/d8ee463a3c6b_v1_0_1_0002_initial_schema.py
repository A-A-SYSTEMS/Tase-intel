"""V1.0.1.0002 initial schema

Full V1.0.1 database schema: all tables, indexes, triggers, functions,
hypertables, and compression policies per DATA_LAYER_SPEC_V1.0.1.md
and IMPLEMENTATION_GUARDRAILS_V1.0.1.md.

Revision ID: d8ee463a3c6b
Revises: cadf71a984a7
Create Date: 2026-04-28 16:36:47.344434
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8ee463a3c6b'
down_revision: Union[str, None] = 'cadf71a984a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==============================================================
    # 0. Enable TimescaleDB extension
    # ==============================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # ==============================================================
    # 1. RAW LAYER (Immutable, Append-Only)
    # ==============================================================

    # -- raw_price_snapshots --
    op.execute("""
        CREATE TABLE raw_price_snapshots (
            ingestion_id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            source_version TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            business_date DATE NOT NULL,
            raw_payload JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            request_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(source, business_date, payload_hash)
        );

        CREATE INDEX idx_raw_prices_source_date
            ON raw_price_snapshots(source, business_date);
        CREATE INDEX idx_raw_prices_fetched
            ON raw_price_snapshots(fetched_at DESC);
    """)

    # -- raw_filings --
    op.execute("""
        CREATE TABLE raw_filings (
            ingestion_id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            source_doc_id TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            filing_published_at TIMESTAMPTZ,
            document_url TEXT NOT NULL,
            document_blob_path TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            document_mime_type TEXT,
            raw_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(source, source_doc_id, document_hash)
        );

        CREATE INDEX idx_raw_filings_source_date
            ON raw_filings(source, filing_published_at);
        CREATE INDEX idx_raw_filings_fetched
            ON raw_filings(fetched_at DESC);
    """)

    # -- raw_news --
    op.execute("""
        CREATE TABLE raw_news (
            ingestion_id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            publisher_claimed_at TIMESTAMPTZ,
            headline TEXT NOT NULL,
            summary TEXT,
            url TEXT NOT NULL,
            url_hash TEXT NOT NULL,
            headline_hash TEXT NOT NULL,
            raw_payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(source, url_hash, headline_hash)
        );

        CREATE INDEX idx_raw_news_url
            ON raw_news(url_hash);
        CREATE INDEX idx_raw_news_fetched
            ON raw_news(fetched_at DESC);
        CREATE INDEX idx_raw_news_source_date
            ON raw_news(source, publisher_claimed_at);
    """)

    # -- raw_macro --
    op.execute("""
        CREATE TABLE raw_macro (
            ingestion_id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            series_id TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            business_date DATE NOT NULL,
            value NUMERIC,
            value_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(source, series_id, business_date, fetched_at)
        );

        CREATE INDEX idx_raw_macro_series
            ON raw_macro(source, series_id, business_date);
    """)

    # ==============================================================
    # 2. STAGING LAYER (Versioned Transformations)
    # ==============================================================

    # -- staging_filings_parsed --
    op.execute("""
        CREATE TABLE staging_filings_parsed (
            parsed_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ingestion_id BIGINT NOT NULL REFERENCES raw_filings(ingestion_id),
            parser_version TEXT NOT NULL,
            parsed_at TIMESTAMPTZ NOT NULL,
            filing_type TEXT,
            filing_subtype TEXT,
            reported_company_name TEXT,
            reported_ticker TEXT,
            reported_isin TEXT,
            extracted_fields JSONB,
            parse_confidence NUMERIC,
            parse_warnings TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(ingestion_id, parser_version)
        );

        CREATE INDEX idx_staging_filings_ingestion
            ON staging_filings_parsed(ingestion_id);
        CREATE INDEX idx_staging_filings_parser
            ON staging_filings_parsed(parser_version);
    """)

    # -- staging_news_tagged --
    op.execute("""
        CREATE TABLE staging_news_tagged (
            tagged_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ingestion_id BIGINT NOT NULL REFERENCES raw_news(ingestion_id),
            tagger_version TEXT NOT NULL,
            tagged_at TIMESTAMPTZ NOT NULL,
            is_relevant BOOLEAN,
            event_type_l1 TEXT,
            event_type_l2 TEXT,
            company_candidates JSONB,
            tagger_confidence NUMERIC,
            tagger_warnings TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(ingestion_id, tagger_version)
        );
    """)

    # -- staging_prices_normalized --
    op.execute("""
        CREATE TABLE staging_prices_normalized (
            normalized_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID,
            business_date DATE NOT NULL,
            primary_source TEXT NOT NULL,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            adj_close NUMERIC,
            volume BIGINT,
            shares_outstanding BIGINT,
            source_versions JSONB,
            reconciliation_status TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(company_id, business_date)
        );
    """)

    # ==============================================================
    # 3. CURATED LAYER (Bitemporal)
    # ==============================================================

    # -- companies --
    op.execute("""
        CREATE TABLE companies (
            company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            canonical_name_he TEXT NOT NULL,
            canonical_name_en TEXT,
            primary_isin TEXT,
            primary_ticker_current TEXT,
            sector TEXT,
            industry_detail TEXT,
            listing_date DATE,
            delisting_date DATE,
            delisting_reason TEXT,
            delisting_successor_company_id UUID,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            valid_from DATE NOT NULL,
            valid_until DATE,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ
        );

        CREATE INDEX idx_companies_active
            ON companies(company_id) WHERE superseded_at IS NULL;
        CREATE INDEX idx_companies_isin
            ON companies(primary_isin) WHERE superseded_at IS NULL;
    """)

    # -- company_tickers_history --
    op.execute("""
        CREATE TABLE company_tickers_history (
            history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(company_id),
            ticker TEXT NOT NULL,
            valid_from DATE NOT NULL,
            valid_until DATE,
            reason TEXT,
            source_filing_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ
        );

        CREATE INDEX idx_tickers_company
            ON company_tickers_history(company_id);
        CREATE INDEX idx_tickers_lookup
            ON company_tickers_history(ticker, valid_from);
    """)

    # -- company_aliases --
    op.execute("""
        CREATE TABLE company_aliases (
            alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(company_id),
            alias_text TEXT NOT NULL,
            alias_normalized TEXT NOT NULL,
            alias_source TEXT,
            confidence NUMERIC,
            valid_from DATE,
            valid_until DATE,
            review_status TEXT,
            reviewer TEXT,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_aliases_normalized
            ON company_aliases(alias_normalized);
        CREATE INDEX idx_aliases_company
            ON company_aliases(company_id);
    """)

    # -- index_membership_history --
    op.execute("""
        CREATE TABLE index_membership_history (
            membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(company_id),
            index_name TEXT NOT NULL,
            valid_from DATE NOT NULL,
            valid_until DATE,
            weight NUMERIC,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ
        );

        CREATE INDEX idx_idxmem_company
            ON index_membership_history(company_id, index_name);
        CREATE INDEX idx_idxmem_lookup
            ON index_membership_history(index_name, valid_from, valid_until);
    """)

    # -- prices_daily (hypertable) --
    op.execute("""
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
            market_cap_ils NUMERIC,
            primary_source TEXT NOT NULL,
            source_priority INT NOT NULL,
            ingestion_lineage JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ,
            PRIMARY KEY (company_id, business_date, recorded_at)
        );

        SELECT create_hypertable('prices_daily', 'business_date',
            chunk_time_interval => INTERVAL '1 year');

        CREATE INDEX idx_prices_active
            ON prices_daily(company_id, business_date)
            WHERE superseded_at IS NULL;
        CREATE INDEX idx_prices_recorded
            ON prices_daily(recorded_at);
    """)

    # -- corporate_actions --
    op.execute("""
        CREATE TABLE corporate_actions (
            action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(company_id),
            action_type TEXT NOT NULL,
            announcement_date DATE,
            ex_date DATE NOT NULL,
            record_date DATE,
            payment_date DATE,
            details JSONB NOT NULL,
            source_filing_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ
        );

        CREATE INDEX idx_corpact_company_date
            ON corporate_actions(company_id, ex_date);
        CREATE INDEX idx_corpact_type
            ON corporate_actions(action_type);
    """)

    # -- intraday_quotes_summary --
    op.execute("""
        CREATE TABLE intraday_quotes_summary (
            company_id UUID NOT NULL REFERENCES companies(company_id),
            business_date DATE NOT NULL,
            avg_bid_ask_spread NUMERIC,
            avg_spread_pct NUMERIC,
            avg_mid_price NUMERIC,
            primary_source TEXT,
            sample_count INT,
            is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
            fallback_tier INT,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ,
            PRIMARY KEY (company_id, business_date, recorded_at)
        );

        CREATE INDEX idx_intraday_summary_active
            ON intraday_quotes_summary(company_id, business_date)
            WHERE superseded_at IS NULL;
        CREATE INDEX idx_intraday_synthetic
            ON intraday_quotes_summary(business_date)
            WHERE is_synthetic = TRUE AND superseded_at IS NULL;
    """)

    # -- events --
    op.execute("""
        CREATE TABLE events (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(company_id),
            event_timestamp TIMESTAMPTZ,
            event_observable_at TIMESTAMPTZ NOT NULL,
            event_type_l1 TEXT NOT NULL,
            event_type_l2 TEXT,
            source_type TEXT NOT NULL,
            source_record_id UUID,
            source_tier INT NOT NULL,
            headline_or_title TEXT,
            features JSONB,
            tagger_version TEXT NOT NULL,
            tagger_confidence NUMERIC,
            is_quarantined BOOLEAN DEFAULT FALSE,
            quarantine_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ
        );

        CREATE INDEX idx_events_company_obs
            ON events(company_id, event_observable_at)
            WHERE superseded_at IS NULL AND is_quarantined = FALSE;
        CREATE INDEX idx_events_obs_at
            ON events(event_observable_at)
            WHERE superseded_at IS NULL;
        CREATE INDEX idx_events_type
            ON events(event_type_l1, event_type_l2);
        CREATE INDEX idx_events_tagger
            ON events(tagger_version);
    """)

    # -- macro_daily --
    op.execute("""
        CREATE TABLE macro_daily (
            series_id TEXT NOT NULL,
            business_date DATE NOT NULL,
            value NUMERIC NOT NULL,
            primary_source TEXT NOT NULL,
            ingestion_lineage JSONB,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ,
            PRIMARY KEY (series_id, business_date, recorded_at)
        );

        CREATE INDEX idx_macro_active
            ON macro_daily(series_id, business_date)
            WHERE superseded_at IS NULL;
    """)

    # -- tase_trading_calendar --
    op.execute("""
        CREATE TABLE tase_trading_calendar (
            business_date DATE PRIMARY KEY,
            is_trading_day BOOLEAN NOT NULL,
            session_type TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # ==============================================================
    # 4. FEATURES LAYER
    # ==============================================================

    # -- features_daily (hypertable) --
    op.execute("""
        CREATE TABLE features_daily (
            company_id UUID NOT NULL REFERENCES companies(company_id),
            feature_date DATE NOT NULL,
            feature_set_version TEXT NOT NULL,
            features JSONB NOT NULL,
            feature_completeness NUMERIC,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, feature_date, feature_set_version)
        );

        SELECT create_hypertable('features_daily', 'feature_date',
            chunk_time_interval => INTERVAL '1 year');
    """)

    # -- features_at_event --
    op.execute("""
        CREATE TABLE features_at_event (
            event_id UUID PRIMARY KEY REFERENCES events(event_id),
            feature_set_version TEXT NOT NULL,
            features JSONB NOT NULL,
            market_cap_bucket TEXT NOT NULL,
            liquidity_bucket TEXT NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            company_id UUID NOT NULL,
            event_observable_at TIMESTAMPTZ NOT NULL,
            CHECK (market_cap_bucket IN ('large', 'mid', 'small')),
            CHECK (liquidity_bucket IN ('large', 'mid', 'small'))
        );

        CREATE INDEX idx_feat_event_obs
            ON features_at_event(event_observable_at);
        CREATE INDEX idx_feat_event_version
            ON features_at_event(feature_set_version);
        CREATE INDEX idx_feat_event_buckets
            ON features_at_event(market_cap_bucket, liquidity_bucket);
    """)

    # ==============================================================
    # 5. AUDIT & LINEAGE
    # ==============================================================

    # -- ingestion_runs --
    op.execute("""
        CREATE TABLE ingestion_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_name TEXT NOT NULL,
            job_version TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            status TEXT NOT NULL,
            records_fetched INT,
            records_inserted INT,
            records_skipped INT,
            error_summary TEXT,
            metadata JSONB
        );

        CREATE INDEX idx_runs_job_time
            ON ingestion_runs(job_name, started_at DESC);
        CREATE INDEX idx_runs_status
            ON ingestion_runs(status, started_at DESC)
            WHERE status IN ('failed', 'partial');
    """)

    # -- data_corrections_log --
    op.execute("""
        CREATE TABLE data_corrections_log (
            correction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name TEXT NOT NULL,
            record_pk JSONB NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            correction_type TEXT,
            source_of_correction TEXT,
            detected_at TIMESTAMPTZ NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            applied_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_corrections_table_time
            ON data_corrections_log(table_name, applied_at DESC);
    """)

    # -- dropped_events_log --
    op.execute("""
        CREATE TABLE dropped_events_log (
            drop_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_record_id UUID,
            drop_reason TEXT NOT NULL,
            drop_details JSONB,
            dropped_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # -- quarantine_log --
    op.execute("""
        CREATE TABLE quarantine_log (
            quarantine_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            released_at TIMESTAMPTZ,
            release_reason TEXT
        );
    """)

    # -- reconciliation_results --
    op.execute("""
        CREATE TABLE reconciliation_results (
            recon_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recon_type TEXT NOT NULL,
            business_date DATE,
            run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            total_compared INT,
            mismatches INT,
            auto_resolved INT,
            manual_review_required INT,
            details JSONB
        );
    """)

    # ==============================================================
    # 6. DECISION LAYER
    # ==============================================================

    # -- decisions_log --
    op.execute("""
        CREATE TABLE decisions_log (
            decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES events(event_id),
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
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

        CREATE INDEX idx_decisions_event
            ON decisions_log(event_id);
        CREATE INDEX idx_decisions_time
            ON decisions_log(decided_at DESC);
        CREATE INDEX idx_decisions_model_version
            ON decisions_log(model_version);
    """)

    # -- model_deployments --
    op.execute("""
        CREATE TABLE model_deployments (
            deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            model_version TEXT NOT NULL,
            deployed_at TIMESTAMPTZ NOT NULL,
            deployed_by TEXT NOT NULL,
            deployment_metadata JSONB,
            superseded_at TIMESTAMPTZ,
            rollback_reason TEXT
        );

        CREATE UNIQUE INDEX idx_model_active
            ON model_deployments(model_version)
            WHERE superseded_at IS NULL;
        CREATE INDEX idx_model_deployed_at
            ON model_deployments(deployed_at DESC);
    """)

    # -- paper_trading_results --
    op.execute("""
        CREATE TABLE paper_trading_results (
            result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            decision_id UUID NOT NULL REFERENCES decisions_log(decision_id),
            entry_date DATE NOT NULL,
            entry_price NUMERIC NOT NULL,
            entry_spread_pct NUMERIC,
            exit_date DATE,
            exit_price NUMERIC,
            exit_spread_pct NUMERIC,
            raw_return NUMERIC,
            net_return_after_costs NUMERIC,
            holding_days INT,
            closed_reason TEXT,
            user_confirmed BOOLEAN NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at TIMESTAMPTZ,
            UNIQUE(decision_id),
            CHECK (user_confirmed = TRUE)
        );

        CREATE INDEX idx_papertrading_decision
            ON paper_trading_results(decision_id);
        CREATE INDEX idx_papertrading_open
            ON paper_trading_results(entry_date)
            WHERE exit_date IS NULL;
        CREATE INDEX idx_papertrading_closed
            ON paper_trading_results(closed_at DESC)
            WHERE exit_date IS NOT NULL;
    """)

    # ==============================================================
    # 7. TRIGGERS — Raw table immutability
    # ==============================================================

    # Trigger function: block UPDATE on raw tables
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_block_raw_update()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'UPDATE on raw table % is forbidden. Raw tables are immutable.', TG_TABLE_NAME;
            RETURN NULL;
        END;
        $$;
    """)

    # Trigger function: block DELETE on raw tables
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_block_raw_delete()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'DELETE on raw table % is forbidden. Raw tables are immutable.', TG_TABLE_NAME;
            RETURN NULL;
        END;
        $$;
    """)

    # Apply triggers to all 4 raw tables
    for raw_table in ['raw_price_snapshots', 'raw_filings', 'raw_news', 'raw_macro']:
        op.execute(f"""
            CREATE TRIGGER trg_{raw_table}_no_update
                BEFORE UPDATE ON {raw_table}
                FOR EACH ROW EXECUTE FUNCTION trg_block_raw_update();
        """)
        op.execute(f"""
            CREATE TRIGGER trg_{raw_table}_no_delete
                BEFORE DELETE ON {raw_table}
                FOR EACH ROW EXECUTE FUNCTION trg_block_raw_delete();
        """)

    # ==============================================================
    # 8. SQL FUNCTIONS — As-of helpers + trading calendar
    # ==============================================================

    # -- prices_daily_as_of --
    op.execute("""
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
    """)

    # -- events_as_of --
    op.execute("""
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
              AND event_observable_at <= p_as_of
              AND recorded_at <= p_as_of
              AND (superseded_at IS NULL OR superseded_at > p_as_of)
              AND is_quarantined = FALSE
            ORDER BY event_id, recorded_at DESC;
        $$;
    """)

    # -- features_at_event_as_of --
    op.execute("""
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
    """)

    # -- companies_as_of --
    op.execute("""
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
    """)

    # -- macro_daily_as_of --
    op.execute("""
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
    """)

    # -- intraday_quotes_summary_as_of --
    op.execute("""
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
    """)

    # -- is_trading_day --
    op.execute("""
        CREATE OR REPLACE FUNCTION is_trading_day(p_date DATE)
        RETURNS BOOLEAN LANGUAGE SQL STABLE AS $$
            SELECT COALESCE(
                (SELECT is_trading_day FROM tase_trading_calendar WHERE business_date = p_date),
                FALSE
            );
        $$;
    """)

    # -- subtract_trading_days --
    op.execute("""
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
    """)

    # -- add_trading_days --
    op.execute("""
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
    """)

    # ==============================================================
    # 9. COMPRESSION POLICIES (TimescaleDB)
    # ==============================================================

    # prices_daily compression
    op.execute("""
        ALTER TABLE prices_daily SET (
            timescaledb.compress,
            timescaledb.compress_orderby = 'business_date DESC',
            timescaledb.compress_segmentby = 'company_id'
        );
        SELECT add_compression_policy('prices_daily', INTERVAL '90 days');
    """)

    # features_daily compression
    op.execute("""
        ALTER TABLE features_daily SET (
            timescaledb.compress,
            timescaledb.compress_orderby = 'feature_date DESC',
            timescaledb.compress_segmentby = 'company_id'
        );
        SELECT add_compression_policy('features_daily', INTERVAL '90 days');
    """)


def downgrade() -> None:
    # ==============================================================
    # Reverse everything in dependency order
    # ==============================================================

    # 9. Remove compression policies first
    op.execute("SELECT remove_compression_policy('features_daily', if_exists => true);")
    op.execute("ALTER TABLE features_daily SET (timescaledb.compress = false);")
    op.execute("SELECT remove_compression_policy('prices_daily', if_exists => true);")
    op.execute("ALTER TABLE prices_daily SET (timescaledb.compress = false);")

    # 8. Drop functions
    op.execute("DROP FUNCTION IF EXISTS add_trading_days(DATE, INT);")
    op.execute("DROP FUNCTION IF EXISTS subtract_trading_days(DATE, INT);")
    op.execute("DROP FUNCTION IF EXISTS is_trading_day(DATE);")
    op.execute("DROP FUNCTION IF EXISTS intraday_quotes_summary_as_of(TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS macro_daily_as_of(TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS companies_as_of(TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS features_at_event_as_of(UUID[], TEXT, TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS events_as_of(TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ);")
    op.execute("DROP FUNCTION IF EXISTS prices_daily_as_of(TIMESTAMPTZ);")

    # 7. Drop triggers then trigger functions
    for raw_table in ['raw_price_snapshots', 'raw_filings', 'raw_news', 'raw_macro']:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{raw_table}_no_delete ON {raw_table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{raw_table}_no_update ON {raw_table};")
    op.execute("DROP FUNCTION IF EXISTS trg_block_raw_delete();")
    op.execute("DROP FUNCTION IF EXISTS trg_block_raw_update();")

    # 6. Decision layer
    op.execute("DROP TABLE IF EXISTS paper_trading_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS model_deployments CASCADE;")
    op.execute("DROP TABLE IF EXISTS decisions_log CASCADE;")

    # 5. Audit & lineage
    op.execute("DROP TABLE IF EXISTS reconciliation_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS quarantine_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS dropped_events_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS data_corrections_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS ingestion_runs CASCADE;")

    # 4. Features layer
    op.execute("DROP TABLE IF EXISTS features_at_event CASCADE;")
    op.execute("DROP TABLE IF EXISTS features_daily CASCADE;")

    # 3. Curated layer (reverse dependency order)
    op.execute("DROP TABLE IF EXISTS tase_trading_calendar CASCADE;")
    op.execute("DROP TABLE IF EXISTS macro_daily CASCADE;")
    op.execute("DROP TABLE IF EXISTS events CASCADE;")
    op.execute("DROP TABLE IF EXISTS intraday_quotes_summary CASCADE;")
    op.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
    op.execute("DROP TABLE IF EXISTS prices_daily CASCADE;")
    op.execute("DROP TABLE IF EXISTS index_membership_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS company_aliases CASCADE;")
    op.execute("DROP TABLE IF EXISTS company_tickers_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS companies CASCADE;")

    # 2. Staging layer
    op.execute("DROP TABLE IF EXISTS staging_prices_normalized CASCADE;")
    op.execute("DROP TABLE IF EXISTS staging_news_tagged CASCADE;")
    op.execute("DROP TABLE IF EXISTS staging_filings_parsed CASCADE;")

    # 1. Raw layer
    op.execute("DROP TABLE IF EXISTS raw_macro CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw_news CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw_filings CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw_price_snapshots CASCADE;")
