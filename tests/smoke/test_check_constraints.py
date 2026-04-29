"""Smoke tests: CHECK constraints reject invalid values.

Each test verifies a CHECK constraint that exists in the migration file.
"""

import pytest
import psycopg.errors

from tests.smoke._helpers import (
    insert_minimal_company,
    insert_minimal_event,
    insert_minimal_features_at_event,
    insert_minimal_decision,
)


class TestFeaturesAtEventBuckets:
    """CHECK constraints on market_cap_bucket and liquidity_bucket."""

    def test_rejects_invalid_market_cap_bucket(self, db_conn):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (market_cap_bucket IN ('large', 'mid', 'small')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)

        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                insert_minimal_features_at_event(
                    db_conn, event_id, company_id, market_cap_bucket="huge"
                )

    def test_rejects_invalid_liquidity_bucket(self, db_conn):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (liquidity_bucket IN ('large', 'mid', 'small')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)

        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                insert_minimal_features_at_event(
                    db_conn, event_id, company_id, liquidity_bucket="tiny"
                )

    @pytest.mark.parametrize("bucket", ["large", "mid", "small"])
    def test_accepts_valid_market_cap_bucket(self, db_conn, bucket):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (market_cap_bucket IN ('large', 'mid', 'small')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)
        insert_minimal_features_at_event(
            db_conn, event_id, company_id, market_cap_bucket=bucket
        )
        cur = db_conn.execute(
            "SELECT market_cap_bucket FROM features_at_event WHERE event_id = %s",
            (str(event_id),),
        )
        assert cur.fetchone()[0] == bucket

    @pytest.mark.parametrize("bucket", ["large", "mid", "small"])
    def test_accepts_valid_liquidity_bucket(self, db_conn, bucket):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (liquidity_bucket IN ('large', 'mid', 'small')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)
        insert_minimal_features_at_event(
            db_conn, event_id, company_id, liquidity_bucket=bucket
        )
        cur = db_conn.execute(
            "SELECT liquidity_bucket FROM features_at_event WHERE event_id = %s",
            (str(event_id),),
        )
        assert cur.fetchone()[0] == bucket


class TestDecisionsLogDecision:
    """CHECK constraint on decisions_log.decision."""

    def test_rejects_invalid_decision(self, db_conn):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (decision IN ('take', 'skip')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)

        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                insert_minimal_decision(db_conn, event_id, decision="maybe")

    @pytest.mark.parametrize("decision", ["take", "skip"])
    def test_accepts_valid_decision(self, db_conn, decision):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (decision IN ('take', 'skip')),
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)
        insert_minimal_decision(db_conn, event_id, decision=decision)
        cur = db_conn.execute(
            "SELECT decision FROM decisions_log WHERE event_id = %s",
            (str(event_id),),
        )
        assert cur.fetchone()[0] == decision


class TestPaperTradingUserConfirmed:
    """CHECK constraint on paper_trading_results.user_confirmed."""

    def test_rejects_unconfirmed(self, db_conn):
        """
        Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
            CHECK (user_confirmed = TRUE)
        """
        company_id = insert_minimal_company(db_conn)
        event_id = insert_minimal_event(db_conn, company_id)
        decision_id = insert_minimal_decision(db_conn, event_id)

        with pytest.raises(psycopg.errors.CheckViolation):
            with db_conn.transaction():
                db_conn.execute(
                    """
                    INSERT INTO paper_trading_results
                      (decision_id, entry_date, entry_price, user_confirmed)
                    VALUES (%s, '2024-06-01', 105.0, FALSE)
                    """,
                    (str(decision_id),),
                )
