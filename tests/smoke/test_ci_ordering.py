"""Smoke tests: decisions_log CI ordering constraint.

Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
    CHECK (p_lower_p10 <= p_point AND p_point <= p_upper_p90)
"""

import pytest
import psycopg.errors

from tests.smoke._helpers import insert_minimal_company, insert_minimal_event, insert_minimal_decision


def test_decisions_log_accepts_valid_ci(db_conn):
    """Valid CI: p10=0.4 <= p_point=0.6 <= p90=0.8."""
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)
    insert_minimal_decision(
        db_conn, event_id, p_lower_p10=0.4, p_point=0.6, p_upper_p90=0.8
    )
    cur = db_conn.execute(
        "SELECT p_point FROM decisions_log WHERE event_id = %s", (str(event_id),)
    )
    assert float(cur.fetchone()[0]) == pytest.approx(0.6)


def test_decisions_log_rejects_p10_above_point(db_conn):
    """Invalid: p10=0.7 > p_point=0.6."""
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            insert_minimal_decision(
                db_conn, event_id, p_lower_p10=0.7, p_point=0.6, p_upper_p90=0.8
            )


def test_decisions_log_rejects_point_above_p90(db_conn):
    """Invalid: p_point=0.85 > p90=0.8."""
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            insert_minimal_decision(
                db_conn, event_id, p_lower_p10=0.4, p_point=0.85, p_upper_p90=0.8
            )


def test_decisions_log_accepts_equal_bounds(db_conn):
    """Valid degenerate CI: p10=p_point=p90=0.5 (constraint uses <=)."""
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)
    insert_minimal_decision(
        db_conn, event_id, p_lower_p10=0.5, p_point=0.5, p_upper_p90=0.5
    )
    cur = db_conn.execute(
        "SELECT p_lower_p10, p_point, p_upper_p90 FROM decisions_log WHERE event_id = %s",
        (str(event_id),),
    )
    row = cur.fetchone()
    assert float(row[0]) == float(row[1]) == float(row[2]) == pytest.approx(0.5)


def test_decisions_log_rejects_inverted_p10_p90(db_conn):
    """Invalid: p10=0.8 > p_point=0.5, p_point=0.5 > p90=0.3."""
    company_id = insert_minimal_company(db_conn)
    event_id = insert_minimal_event(db_conn, company_id)

    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            insert_minimal_decision(
                db_conn, event_id, p_lower_p10=0.8, p_point=0.5, p_upper_p90=0.3
            )
