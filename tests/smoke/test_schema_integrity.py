"""Smoke tests: schema integrity — verify all required DB artifacts exist."""


def test_all_required_tables_exist(db_conn):
    """All tables listed in IMPLEMENTATION_GUARDRAILS §3 must exist."""
    expected_tables = [
        "raw_price_snapshots",
        "raw_filings",
        "raw_news",
        "raw_macro",
        "staging_filings_parsed",
        "staging_news_tagged",
        "staging_prices_normalized",
        "companies",
        "company_tickers_history",
        "company_aliases",
        "index_membership_history",
        "prices_daily",
        "corporate_actions",
        "intraday_quotes_summary",
        "events",
        "macro_daily",
        "tase_trading_calendar",
        "features_daily",
        "features_at_event",
        "ingestion_runs",
        "data_corrections_log",
        "dropped_events_log",
        "quarantine_log",
        "reconciliation_results",
        "decisions_log",
        "model_deployments",
        "paper_trading_results",
    ]

    cur = db_conn.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    actual_tables = {row[0] for row in cur.fetchall()}

    missing = [t for t in expected_tables if t not in actual_tables]
    assert not missing, f"Missing tables: {missing}"


def test_all_required_functions_exist(db_conn):
    """All functions listed in IMPLEMENTATION_GUARDRAILS §3 must exist."""
    expected_functions = [
        "prices_daily_as_of",
        "events_as_of",
        "features_at_event_as_of",
        "companies_as_of",
        "macro_daily_as_of",
        "intraday_quotes_summary_as_of",
        "is_trading_day",
        "subtract_trading_days",
        "add_trading_days",
        # Trigger functions (immutability enforcement)
        "trg_block_raw_update",
        "trg_block_raw_delete",
    ]

    cur = db_conn.execute(
        """
        SELECT routine_name FROM information_schema.routines
        WHERE routine_schema = 'public'
        """
    )
    actual_functions = {row[0] for row in cur.fetchall()}

    missing = [f for f in expected_functions if f not in actual_functions]
    assert not missing, f"Missing functions: {missing}"


def test_all_required_hypertables_exist(db_conn):
    """prices_daily and features_daily must be registered as TimescaleDB hypertables."""
    expected_hypertables = ["prices_daily", "features_daily"]

    cur = db_conn.execute(
        """
        SELECT hypertable_name
        FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public'
        """
    )
    actual_hypertables = {row[0] for row in cur.fetchall()}

    missing = [h for h in expected_hypertables if h not in actual_hypertables]
    assert not missing, f"Missing hypertables: {missing}"
