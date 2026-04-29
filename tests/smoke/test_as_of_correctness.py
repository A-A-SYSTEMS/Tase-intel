"""Smoke tests: as-of functions correctly hide future-recorded data.

These tests validate the bitemporal leakage guarantee — the most critical
property of the system.

Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
    CREATE OR REPLACE FUNCTION prices_daily_as_of(p_as_of TIMESTAMPTZ)
    RETURNS TABLE (company_id UUID, business_date DATE, close NUMERIC,
                   adj_close NUMERIC, volume BIGINT, market_cap_ils NUMERIC)
    ...
        WHERE recorded_at <= p_as_of
          AND (superseded_at IS NULL OR superseded_at > p_as_of)

    CREATE OR REPLACE FUNCTION events_as_of(
        p_window_start TIMESTAMPTZ, p_window_end TIMESTAMPTZ, p_as_of TIMESTAMPTZ)
    RETURNS SETOF events
    ...
        WHERE event_observable_at >= p_window_start
          AND event_observable_at <= p_window_end
          AND event_observable_at <= p_as_of
          AND recorded_at <= p_as_of
          AND (superseded_at IS NULL OR superseded_at > p_as_of)
          AND is_quarantined = FALSE
"""

import uuid

from tests.smoke._helpers import insert_minimal_company, insert_minimal_event


class TestPricesDailyAsOf:
    """Bitemporal correctness of prices_daily_as_of()."""

    def _setup_price_correction(self, db_conn):
        """Insert a company with two price records simulating a correction."""
        company_id = insert_minimal_company(db_conn)

        # Row A: original price, recorded on 2024-03-01, superseded on 2024-03-15
        db_conn.execute(
            """
            INSERT INTO prices_daily
              (company_id, business_date, close, adj_close,
               primary_source, source_priority, ingestion_lineage,
               recorded_at, superseded_at)
            VALUES (%s, '2024-02-20', 100.0, 100.0,
                    'tase', 1, '{}'::jsonb,
                    '2024-03-01 10:00+00', '2024-03-15 10:00+00')
            """,
            (str(company_id),),
        )

        # Row B: corrected price, recorded on 2024-03-15, not superseded
        db_conn.execute(
            """
            INSERT INTO prices_daily
              (company_id, business_date, close, adj_close,
               primary_source, source_priority, ingestion_lineage,
               recorded_at, superseded_at)
            VALUES (%s, '2024-02-20', 105.0, 105.0,
                    'tase', 1, '{}'::jsonb,
                    '2024-03-15 10:00+00', NULL)
            """,
            (str(company_id),),
        )

        return company_id

    def test_returns_original_before_correction(self, db_conn):
        """As-of before correction → see original (close=100)."""
        company_id = self._setup_price_correction(db_conn)

        cur = db_conn.execute(
            """
            SELECT close FROM prices_daily_as_of('2024-03-10 12:00+00'::timestamptz)
            WHERE company_id = %s AND business_date = '2024-02-20'
            """,
            (str(company_id),),
        )
        row = cur.fetchone()
        assert row is not None, "Expected Row A visible before correction"
        assert float(row[0]) == 100.0

    def test_returns_corrected_after_correction(self, db_conn):
        """As-of after correction → see corrected (close=105)."""
        company_id = self._setup_price_correction(db_conn)

        cur = db_conn.execute(
            """
            SELECT close FROM prices_daily_as_of('2024-04-01 12:00+00'::timestamptz)
            WHERE company_id = %s AND business_date = '2024-02-20'
            """,
            (str(company_id),),
        )
        row = cur.fetchone()
        assert row is not None, "Expected Row B visible after correction"
        assert float(row[0]) == 105.0

    def test_at_correction_boundary(self, db_conn):
        """
        As-of at exact correction moment (2024-03-15 10:00 UTC).
        Row A: superseded_at = as_of → NOT visible (condition: superseded_at > as_of is FALSE).
        Row B: recorded_at = as_of → visible (condition: recorded_at <= as_of is TRUE).
        Expect Row B (close=105).
        """
        company_id = self._setup_price_correction(db_conn)

        cur = db_conn.execute(
            """
            SELECT close FROM prices_daily_as_of('2024-03-15 10:00+00'::timestamptz)
            WHERE company_id = %s AND business_date = '2024-02-20'
            """,
            (str(company_id),),
        )
        row = cur.fetchone()
        assert row is not None, "Expected Row B visible at correction boundary"
        assert float(row[0]) == 105.0


class TestEventsAsOf:
    """Bitemporal + observability correctness of events_as_of()."""

    def test_excludes_future_observable(self, db_conn):
        """
        Event with event_observable_at in the future relative to as_of.
        The function requires: event_observable_at <= p_as_of.
        """
        company_id = insert_minimal_company(db_conn)

        # Event observable at 2024-06-01, recorded at 2024-05-01
        event_id = uuid.uuid4()
        db_conn.execute(
            """
            INSERT INTO events
              (event_id, company_id, event_observable_at, event_type_l1,
               source_type, source_tier, tagger_version, recorded_at)
            VALUES (%s, %s, '2024-06-01 09:00+00', 'filing', 'maya', 1, 'v1.0',
                    '2024-05-01 10:00+00')
            """,
            (str(event_id), str(company_id)),
        )

        # Query as_of 2024-04-01 — event not yet observable
        cur = db_conn.execute(
            """
            SELECT event_id FROM events_as_of(
                '2024-01-01'::timestamptz,
                '2024-12-31'::timestamptz,
                '2024-04-01'::timestamptz
            ) WHERE event_id = %s
            """,
            (str(event_id),),
        )
        assert cur.fetchone() is None, "Future-observable event should be hidden"

    def test_excludes_quarantined(self, db_conn):
        """Quarantined events excluded regardless of time window."""
        company_id = insert_minimal_company(db_conn)

        event_id = uuid.uuid4()
        db_conn.execute(
            """
            INSERT INTO events
              (event_id, company_id, event_observable_at, event_type_l1,
               source_type, source_tier, tagger_version, recorded_at,
               is_quarantined, quarantine_reason)
            VALUES (%s, %s, '2024-03-01 09:00+00', 'filing', 'maya', 1, 'v1.0',
                    '2024-03-01 10:00+00', TRUE, 'data quality issue')
            """,
            (str(event_id), str(company_id)),
        )

        # Query with permissive timeframe — should still be excluded
        cur = db_conn.execute(
            """
            SELECT event_id FROM events_as_of(
                '2024-01-01'::timestamptz,
                '2024-12-31'::timestamptz,
                '2024-12-31'::timestamptz
            ) WHERE event_id = %s
            """,
            (str(event_id),),
        )
        assert cur.fetchone() is None, "Quarantined event should be excluded"

    def test_excludes_future_recorded(self, db_conn):
        """
        Event with recorded_at after the as_of timestamp.
        The function requires: recorded_at <= p_as_of.
        """
        company_id = insert_minimal_company(db_conn)

        event_id = uuid.uuid4()
        db_conn.execute(
            """
            INSERT INTO events
              (event_id, company_id, event_observable_at, event_type_l1,
               source_type, source_tier, tagger_version, recorded_at)
            VALUES (%s, %s, '2024-03-01 09:00+00', 'filing', 'maya', 1, 'v1.0',
                    '2024-06-01 10:00+00')
            """,
            (str(event_id), str(company_id)),
        )

        # Query as_of 2024-04-01 — event recorded after this point
        cur = db_conn.execute(
            """
            SELECT event_id FROM events_as_of(
                '2024-01-01'::timestamptz,
                '2024-12-31'::timestamptz,
                '2024-04-01'::timestamptz
            ) WHERE event_id = %s
            """,
            (str(event_id),),
        )
        assert cur.fetchone() is None, "Future-recorded event should be hidden"
