"""
Smoke tests for the tase_trading_calendar seed.

Layer 1: Pure function tests (no DB).
Layer 2: DB tests (transactional rollback via db_conn fixture).
"""
from datetime import date

import pytest

from scripts.seed_calendar import (
    build_rows,
    default_end_date,
    default_start_date,
    is_tase_trading_day,
    upsert_calendar,
)


# ===================================================================
# Layer 1 — Pure function tests (no DB)
# ===================================================================


class TestIsTaseTradingDay:
    """
    TASE trades Sunday through Thursday.
    Verify against known dates whose weekday is unambiguous.
    """

    def test_sunday_is_trading(self):
        # 2025-01-05 is a Sunday
        assert is_tase_trading_day(date(2025, 1, 5)) is True

    def test_monday_is_trading(self):
        assert is_tase_trading_day(date(2025, 1, 6)) is True

    def test_tuesday_is_trading(self):
        assert is_tase_trading_day(date(2025, 1, 7)) is True

    def test_wednesday_is_trading(self):
        assert is_tase_trading_day(date(2025, 1, 8)) is True

    def test_thursday_is_trading(self):
        assert is_tase_trading_day(date(2025, 1, 9)) is True

    def test_friday_is_not_trading(self):
        assert is_tase_trading_day(date(2025, 1, 10)) is False

    def test_saturday_is_not_trading(self):
        assert is_tase_trading_day(date(2025, 1, 11)) is False

    def test_full_week_pattern(self):
        """Iterate Sun 2025-01-05 through Sat 2025-01-11."""
        results = [
            (date(2025, 1, day), is_tase_trading_day(date(2025, 1, day)))
            for day in range(5, 12)
        ]
        expected = [
            (date(2025, 1, 5), True),    # Sun
            (date(2025, 1, 6), True),    # Mon
            (date(2025, 1, 7), True),    # Tue
            (date(2025, 1, 8), True),    # Wed
            (date(2025, 1, 9), True),    # Thu
            (date(2025, 1, 10), False),  # Fri
            (date(2025, 1, 11), False),  # Sat
        ]
        assert results == expected


def test_default_start_is_jan_1_five_years_back():
    assert default_start_date(date(2026, 4, 29)) == date(2021, 1, 1)


def test_default_end_is_dec_31_one_year_forward():
    assert default_end_date(date(2026, 4, 29)) == date(2027, 12, 31)


# ===================================================================
# Layer 2 — DB tests (rollback-isolated via db_conn)
# ===================================================================


def test_seed_inserts_correct_count(db_conn):
    """A small range produces the expected number of rows."""
    rows = build_rows(date(2025, 1, 5), date(2025, 1, 11))  # one full week
    upsert_calendar(db_conn, rows)

    cur = db_conn.execute(
        "SELECT COUNT(*), "
        "       COUNT(*) FILTER (WHERE is_trading_day = TRUE) "
        "FROM tase_trading_calendar "
        "WHERE business_date BETWEEN %s AND %s",
        (date(2025, 1, 5), date(2025, 1, 11)),
    )
    total, trading = cur.fetchone()
    assert total == 7
    assert trading == 5  # Sun-Thu


def test_seed_is_idempotent(db_conn):
    """Re-running the seed on the same range produces the same final state."""
    rows = build_rows(date(2025, 1, 5), date(2025, 1, 11))
    upsert_calendar(db_conn, rows)
    upsert_calendar(db_conn, rows)  # second time
    upsert_calendar(db_conn, rows)  # third, for paranoia

    cur = db_conn.execute(
        "SELECT COUNT(*) FROM tase_trading_calendar "
        "WHERE business_date BETWEEN %s AND %s",
        (date(2025, 1, 5), date(2025, 1, 11)),
    )
    assert cur.fetchone()[0] == 7  # still 7, not 21


def test_seed_corrects_manually_modified_row(db_conn):
    """If a row is manually wrong, re-seed brings it back to canonical."""
    rows = build_rows(date(2025, 1, 5), date(2025, 1, 11))
    upsert_calendar(db_conn, rows)

    # Maliciously flip Friday to "trading day."
    db_conn.execute(
        "UPDATE tase_trading_calendar SET is_trading_day = TRUE WHERE business_date = %s",
        (date(2025, 1, 10),),  # Friday
    )

    # Verify it was flipped.
    cur = db_conn.execute(
        "SELECT is_trading_day FROM tase_trading_calendar WHERE business_date = %s",
        (date(2025, 1, 10),),
    )
    assert cur.fetchone()[0] is True  # incorrectly TRUE now

    # Re-seed.
    upsert_calendar(db_conn, rows)

    # Verify it was corrected back to FALSE.
    cur = db_conn.execute(
        "SELECT is_trading_day FROM tase_trading_calendar WHERE business_date = %s",
        (date(2025, 1, 10),),
    )
    assert cur.fetchone()[0] is False  # corrected
