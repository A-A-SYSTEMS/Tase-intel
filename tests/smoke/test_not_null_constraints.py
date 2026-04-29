"""Smoke tests: NOT NULL constraints on critical columns.

Each test verifies a NOT NULL constraint that exists in the migration file.
"""

import pytest
import psycopg.errors

from tests.smoke._helpers import (
    insert_minimal_company,
    insert_minimal_event,
)


def test_features_at_event_market_cap_bucket_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        market_cap_bucket TEXT NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO features_at_event
                  (event_id, feature_set_version, features,
                   market_cap_bucket, liquidity_bucket,
                   company_id, event_observable_at)
                VALUES (%s, 'v1.0', '{}'::jsonb,
                        NULL, 'mid', %s, now())
                """,
                (str(event_id), str(company_id)),
            )


def test_features_at_event_liquidity_bucket_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        liquidity_bucket TEXT NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO features_at_event
                  (event_id, feature_set_version, features,
                   market_cap_bucket, liquidity_bucket,
                   company_id, event_observable_at)
                VALUES (%s, 'v1.0', '{}'::jsonb,
                        'mid', NULL, %s, now())
                """,
                (str(event_id), str(company_id)),
            )


def test_decisions_log_decision_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        decision TEXT NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO decisions_log
                  (event_id, decision, reason, p_point, p_lower_p10,
                   p_upper_p90, threshold_applied, model_version, feature_set_version)
                VALUES (%s, NULL, 'reason', 0.6, 0.4, 0.8, 0.55, 'v1.0', 'v1.0')
                """,
                (str(event_id),),
            )


def test_decisions_log_event_id_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        event_id UUID NOT NULL REFERENCES events(event_id),
    """
    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO decisions_log
                  (event_id, decision, reason, p_point, p_lower_p10,
                   p_upper_p90, threshold_applied, model_version, feature_set_version)
                VALUES (NULL, 'take', 'reason', 0.6, 0.4, 0.8, 0.55, 'v1.0', 'v1.0')
                """
            )


def test_decisions_log_p_point_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        p_point NUMERIC NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO decisions_log
                  (event_id, decision, reason, p_point, p_lower_p10,
                   p_upper_p90, threshold_applied, model_version, feature_set_version)
                VALUES (%s, 'take', 'reason', NULL, 0.4, 0.8, 0.55, 'v1.0', 'v1.0')
                """,
                (str(event_id),),
            )


def test_events_event_observable_at_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        event_observable_at TIMESTAMPTZ NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO events
                  (company_id, event_observable_at, event_type_l1,
                   source_type, source_tier, tagger_version)
                VALUES (%s, NULL, 'filing', 'maya', 1, 'v1.0')
                """,
                (str(company_id),),
            )


def test_prices_daily_close_not_null(db_conn):
    """
    Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
        close NUMERIC NOT NULL,
    """
    company_id = insert_minimal_company(db_conn)

    with pytest.raises(psycopg.errors.NotNullViolation):
        with db_conn.transaction():
            db_conn.execute(
                """
                INSERT INTO prices_daily
                  (company_id, business_date, close, adj_close,
                   primary_source, source_priority, ingestion_lineage, recorded_at)
                VALUES (%s, '2024-01-15', NULL, 100.0,
                        'tase', 1, '{}'::jsonb, now())
                """,
                (str(company_id),),
            )
