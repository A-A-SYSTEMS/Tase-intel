"""
Self-tests for the forbidden-pattern scanner.

These prove the scanner actually detects (and ignores) the right things.
Without these, the real-repo lint tests could pass vacuously.
"""
from src.lint.forbidden_patterns import (
    detect_pattern_1_embargo,
    detect_pattern_2_same_day_close,
    detect_pattern_3_bitemporal_bypass,
)


# ===================================================================
# Pattern 1 — Calendar-day embargo arithmetic
# ===================================================================

def test_p1_detects_embargo_in_comment_above(tmp_path):
    """timedelta(days=N) within 5 lines of 'embargo' → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        "from datetime import timedelta\n"
        "def f():\n"
        "    # embargo before test set\n"
        "    return timedelta(days=5)\n"
    )
    violations = detect_pattern_1_embargo(tmp_path)
    assert len(violations) == 1
    assert violations[0].line_number == 4
    assert violations[0].rule == "P1_calendar_day_embargo"


def test_p1_detects_embargo_inline_comment(tmp_path):
    """timedelta(days=N) with inline 'embargo' comment → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        "from datetime import timedelta\n"
        "x = timedelta(days=5)  # embargo window\n"
    )
    violations = detect_pattern_1_embargo(tmp_path)
    assert len(violations) == 1
    assert violations[0].line_number == 2


def test_p1_ignores_timedelta_unrelated_to_embargo(tmp_path):
    """timedelta(days=N) without 'embargo' nearby → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        "from datetime import timedelta\n"
        "def cache_ttl():\n"
        "    return timedelta(days=7)\n"
    )
    violations = detect_pattern_1_embargo(tmp_path)
    assert violations == []


def test_p1_ignores_embargo_far_away(tmp_path):
    """timedelta(days=N) with 'embargo' more than 5 lines away → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    lines = [
        "# embargo logic here\n",          # line 1
        "pass\n",                            # line 2
        "pass\n",                            # line 3
        "pass\n",                            # line 4
        "pass\n",                            # line 5
        "pass\n",                            # line 6
        "pass\n",                            # line 7  (7 lines away from embargo)
        "x = timedelta(days=5)\n",           # line 8  (> 5 lines from line 1)
    ]
    (src / "fake.py").write_text("".join(lines))
    violations = detect_pattern_1_embargo(tmp_path)
    assert violations == []


# ===================================================================
# Pattern 2 — Same-day close reference
# ===================================================================

def test_p2_detects_same_day_close_sql(tmp_path):
    """business_date = DATE(event_observable_at) in .sql → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.sql").write_text(
        "SELECT p.close FROM prices_daily p\n"
        "WHERE p.business_date = DATE(e.event_observable_at)\n"
    )
    violations = detect_pattern_2_same_day_close(tmp_path)
    assert len(violations) == 1
    assert violations[0].rule == "P2_same_day_close"


def test_p2_detects_same_day_close_python(tmp_path):
    """business_date = DATE(event_observable_at) embedded in .py → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        'sql = """\n'
        "WHERE business_date = DATE( event_observable_at )\n"
        '"""\n'
    )
    violations = detect_pattern_2_same_day_close(tmp_path)
    assert len(violations) == 1


def test_p2_ignores_subtract_trading_days(tmp_path):
    """Legitimate pattern using subtract_trading_days → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.sql").write_text(
        "SELECT p.close FROM prices_daily p\n"
        "WHERE p.business_date = subtract_trading_days(DATE(e.event_observable_at), 1)\n"
    )
    violations = detect_pattern_2_same_day_close(tmp_path)
    assert violations == []


def test_p2_ignores_unrelated_business_date(tmp_path):
    """business_date used without DATE(event_observable_at) → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.sql").write_text(
        "SELECT * FROM prices_daily_as_of(now())\n"
        "WHERE business_date = '2024-01-01'\n"
    )
    violations = detect_pattern_2_same_day_close(tmp_path)
    assert violations == []


# ===================================================================
# Pattern 3 — Bitemporal table direct query (no _as_of wrapper)
# ===================================================================

def test_p3_detects_direct_from_events(tmp_path):
    """FROM events (not _as_of) in .py → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        'sql = "SELECT * FROM events WHERE event_observable_at > now()"\n'
    )
    violations = detect_pattern_3_bitemporal_bypass(tmp_path)
    assert len(violations) == 1
    assert violations[0].rule == "P3_bitemporal_bypass"


def test_p3_detects_direct_from_prices_daily(tmp_path):
    """FROM prices_daily (not _as_of) in .sql → violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.sql").write_text(
        "SELECT close FROM prices_daily WHERE company_id = 1\n"
    )
    violations = detect_pattern_3_bitemporal_bypass(tmp_path)
    assert len(violations) == 1


def test_p3_allows_events_as_of(tmp_path):
    """FROM events_as_of(...) → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.py").write_text(
        'sql = "SELECT * FROM events_as_of(now())"\n'
    )
    violations = detect_pattern_3_bitemporal_bypass(tmp_path)
    assert violations == []


def test_p3_allows_prices_daily_as_of(tmp_path):
    """FROM prices_daily_as_of(...) → no violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "fake.sql").write_text(
        "SELECT close FROM prices_daily_as_of(:as_of) WHERE company_id = 1\n"
    )
    violations = detect_pattern_3_bitemporal_bypass(tmp_path)
    assert violations == []


def test_p3_skips_migrations_versions(tmp_path):
    """Migrations are allowed to reference bitemporal tables directly."""
    mig_dir = tmp_path / "src" / "migrations" / "versions"
    mig_dir.mkdir(parents=True)
    (mig_dir / "fake_revision.py").write_text(
        'op.execute("CREATE TABLE events (...)")\n'
        'op.execute("ALTER TABLE events ADD COLUMN x INT")\n'
        'op.execute("INSERT INTO events SELECT * FROM events")\n'
    )
    violations = detect_pattern_3_bitemporal_bypass(tmp_path)
    assert violations == []
