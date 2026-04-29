#!/usr/bin/env python3
"""
Seed the tase_trading_calendar table.

V1.0.1 calendar:
  - Sunday through Thursday -> is_trading_day = TRUE
  - Friday and Saturday     -> is_trading_day = FALSE
  - No holidays (deferred to a later batch)

Idempotent: rerunning corrects any manually edited rows back to canonical.
Source of truth: this script. Do not modify rows manually in production.

Usage:
  python scripts/seed_calendar.py                                        # 5 yrs back, 1 yr forward
  python scripts/seed_calendar.py --start YYYY-MM-DD --end YYYY-MM-DD   # explicit range
  python scripts/seed_calendar.py --dry-run                              # print stats, no DB changes
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

import psycopg
from dotenv import load_dotenv


def is_tase_trading_day(d: date) -> bool:
    """
    TASE trades Sunday through Thursday.
    Python's date.weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6.
    Non-trading days are Friday (4) and Saturday (5).
    """
    return d.weekday() not in (4, 5)


def default_start_date(today: date) -> date:
    """Five years back, rounded to January 1 of that year."""
    return date(today.year - 5, 1, 1)


def default_end_date(today: date) -> date:
    """One year forward, rounded to December 31 of that year."""
    return date(today.year + 1, 12, 31)


def iter_dates(start: date, end: date):
    """Yield every date in [start, end] inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def build_rows(start: date, end: date) -> list[tuple[date, bool, str | None, str | None]]:
    """
    Build the full set of (business_date, is_trading_day, session_type, notes) tuples.
    session_type and notes are None for V1.0.1 (no half-days, no annotations).
    """
    return [
        (d, is_tase_trading_day(d), None, None)
        for d in iter_dates(start, end)
    ]


def upsert_calendar(conn: psycopg.Connection, rows: list[tuple]) -> dict[str, int]:
    """
    Upsert rows into tase_trading_calendar.

    Uses ON CONFLICT DO UPDATE so re-runs correct any drift.
    """
    sql = """
        INSERT INTO tase_trading_calendar
            (business_date, is_trading_day, session_type, notes)
        VALUES
            (%s, %s, %s, %s)
        ON CONFLICT (business_date) DO UPDATE SET
            is_trading_day = EXCLUDED.is_trading_day,
            session_type   = EXCLUDED.session_type,
            notes          = EXCLUDED.notes
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return {"rows_attempted": len(rows)}


def get_summary(conn: psycopg.Connection, start: date, end: date) -> dict[str, int]:
    """Read back the post-seed state for verification."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM tase_trading_calendar "
            "WHERE business_date BETWEEN %s AND %s",
            (start, end),
        )
        total = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM tase_trading_calendar "
            "WHERE business_date BETWEEN %s AND %s AND is_trading_day = TRUE",
            (start, end),
        )
        trading = cur.fetchone()[0]

        return {"total_days": total, "trading_days": trading, "non_trading_days": total - trading}


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Seed tase_trading_calendar.")
    parser.add_argument("--start", type=date.fromisoformat, default=None,
                        help="Start date (YYYY-MM-DD). Defaults to 5y back, Jan 1.")
    parser.add_argument("--end", type=date.fromisoformat, default=None,
                        help="End date (YYYY-MM-DD). Defaults to 1y forward, Dec 31.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended changes; make no DB modifications.")
    args = parser.parse_args()

    today = date.today()
    start = args.start or default_start_date(today)
    end = args.end or default_end_date(today)

    if start > end:
        print(f"ERROR: start ({start}) is after end ({end}).", file=sys.stderr)
        return 2

    rows = build_rows(start, end)
    print(f"Range: {start} to {end} ({len(rows)} days).")

    if args.dry_run:
        trading = sum(1 for _, t, _, _ in rows if t)
        print(f"Dry-run: would upsert {len(rows)} rows ({trading} trading, {len(rows) - trading} non-trading).")
        return 0

    # Build DB URL from env parts (same logic as alembic env.py)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        user = os.environ.get("POSTGRES_USER", "tase_intel")
        password = os.environ.get("POSTGRES_PASSWORD")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        dbname = os.environ.get("POSTGRES_DB", "tase_intel")
        if not password:
            print("ERROR: DATABASE_URL or POSTGRES_PASSWORD not set (check .env).", file=sys.stderr)
            return 2
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    # Strip SQLAlchemy driver prefix if present (psycopg needs plain postgresql://)
    if db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(db_url, autocommit=False) as conn:
        stats = upsert_calendar(conn, rows)
        conn.commit()
        summary = get_summary(conn, start, end)

    print(f"Upserted {stats['rows_attempted']} rows.")
    print(f"Verified in DB ({start} to {end}):")
    print(f"  Total days:        {summary['total_days']}")
    print(f"  Trading days:      {summary['trading_days']}")
    print(f"  Non-trading days:  {summary['non_trading_days']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
