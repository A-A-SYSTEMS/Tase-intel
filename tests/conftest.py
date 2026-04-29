import os

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def db_url() -> str:
    """Build a psycopg-compatible connection string from environment variables."""
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB")
    if not all([user, password, dbname]):
        pytest.fail(
            "Database env vars not set. Ensure POSTGRES_USER, POSTGRES_PASSWORD, "
            "POSTGRES_DB are defined in .env"
        )
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="session")
def _migration_head_check(db_url: str) -> None:
    """
    Pre-flight: verify the DB is at the expected migration head.
    Aborts the test session if not.
    """
    expected_head = "d8ee463a3c6b"  # V1.0.1.0002
    with psycopg.connect(db_url) as conn:
        cur = conn.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        if row is None:
            pytest.fail("alembic_version table is empty; no migration applied")
        actual = row[0]
        if actual != expected_head:
            pytest.fail(
                f"Migration head mismatch: expected {expected_head}, got {actual}. "
                "Run `make migrate` first."
            )


@pytest.fixture
def db_conn(db_url: str, _migration_head_check):
    """
    Per-test connection with rollback isolation.
    Opens a connection, begins a transaction, yields the connection,
    rolls back unconditionally on teardown. Never commits.
    """
    conn = psycopg.connect(db_url, autocommit=False)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
