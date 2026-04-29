"""Minimal fixture helpers for smoke tests.

Each helper inserts the bare-minimum valid row to satisfy FK and NOT NULL
constraints. They do NOT commit — the caller's transaction controls lifecycle.
"""

import uuid


def insert_minimal_company(conn) -> uuid.UUID:
    """Insert a minimal valid companies row. Returns company_id."""
    company_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO companies (
            company_id, canonical_name_he, valid_from, recorded_at
        ) VALUES (%s, %s, %s, now())
        """,
        (str(company_id), "חברת בדיקה", "2020-01-01"),
    )
    return company_id


def insert_minimal_event(conn, company_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal valid events row. Returns event_id."""
    event_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO events (
            event_id, company_id, event_observable_at,
            event_type_l1, source_type, source_tier, tagger_version,
            recorded_at
        ) VALUES (%s, %s, now(), %s, %s, %s, %s, now())
        """,
        (str(event_id), str(company_id), "filing", "maya", 1, "v1.0"),
    )
    return event_id


def insert_minimal_features_at_event(
    conn,
    event_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    market_cap_bucket: str = "mid",
    liquidity_bucket: str = "mid",
    features: str = "{}",
) -> None:
    """Insert a minimal valid features_at_event row."""
    conn.execute(
        """
        INSERT INTO features_at_event (
            event_id, feature_set_version, features,
            market_cap_bucket, liquidity_bucket,
            company_id, event_observable_at
        ) VALUES (%s, 'v1.0', %s::jsonb, %s, %s, %s, now())
        """,
        (str(event_id), features, market_cap_bucket, liquidity_bucket, str(company_id)),
    )


def insert_minimal_decision(
    conn,
    event_id: uuid.UUID,
    *,
    p_point: float = 0.6,
    p_lower_p10: float = 0.4,
    p_upper_p90: float = 0.8,
    decision: str = "take",
) -> uuid.UUID:
    """Insert a minimal valid decisions_log row. Returns decision_id."""
    decision_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO decisions_log (
            decision_id, event_id, decision, reason,
            p_point, p_lower_p10, p_upper_p90,
            threshold_applied, model_version, feature_set_version
        ) VALUES (%s, %s, %s, 'test reason', %s, %s, %s, 0.55, 'v1.0', 'v1.0')
        """,
        (
            str(decision_id),
            str(event_id),
            decision,
            p_point,
            p_lower_p10,
            p_upper_p90,
        ),
    )
    return decision_id
