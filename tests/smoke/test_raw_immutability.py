"""Smoke tests: raw_* tables reject UPDATE and DELETE (immutability triggers).

Migration source (src/migrations/versions/d8ee463a3c6b_..._initial_schema.py):
    CREATE OR REPLACE FUNCTION trg_block_raw_update() ...
        RAISE EXCEPTION 'UPDATE on raw table % is forbidden. Raw tables are immutable.'
    CREATE OR REPLACE FUNCTION trg_block_raw_delete() ...
        RAISE EXCEPTION 'DELETE on raw table % is forbidden. Raw tables are immutable.'
    Triggers applied to: raw_price_snapshots, raw_filings, raw_news, raw_macro
"""

import pytest
import psycopg.errors


# Minimal valid INSERT statements per raw table
RAW_TABLE_INSERTS = {
    "raw_price_snapshots": """
        INSERT INTO raw_price_snapshots
          (source, source_version, fetched_at, business_date, raw_payload, payload_hash)
        VALUES ('test', 'v1', now(), '2024-01-15', '{}'::jsonb, 'hash_test_001')
        RETURNING ingestion_id
    """,
    "raw_filings": """
        INSERT INTO raw_filings
          (source, source_doc_id, fetched_at, document_url, document_blob_path, document_hash)
        VALUES ('test', 'doc_001', now(), 'http://test.com/doc', '/tmp/doc', 'hash_test_001')
        RETURNING ingestion_id
    """,
    "raw_news": """
        INSERT INTO raw_news
          (source, fetched_at, headline, url, url_hash, headline_hash, raw_payload)
        VALUES ('test', now(), 'Test headline', 'http://test.com/news', 'url_hash_001', 'hl_hash_001', '{}'::jsonb)
        RETURNING ingestion_id
    """,
    "raw_macro": """
        INSERT INTO raw_macro
          (source, series_id, fetched_at, business_date, value)
        VALUES ('test', 'VIX', now(), '2024-01-15', 15.5)
        RETURNING ingestion_id
    """,
}


@pytest.mark.parametrize("table", list(RAW_TABLE_INSERTS.keys()))
def test_raw_table_allows_insert(db_conn, table):
    """Raw tables allow INSERT (append-only)."""
    cur = db_conn.execute(RAW_TABLE_INSERTS[table])
    row = cur.fetchone()
    assert row is not None
    assert row[0] > 0  # ingestion_id returned


@pytest.mark.parametrize("table", list(RAW_TABLE_INSERTS.keys()))
def test_raw_table_rejects_update(db_conn, table):
    """Raw tables reject UPDATE via trg_block_raw_update trigger."""
    cur = db_conn.execute(RAW_TABLE_INSERTS[table])
    ingestion_id = cur.fetchone()[0]

    with pytest.raises(psycopg.errors.RaiseException):
        with db_conn.transaction():
            db_conn.execute(
                f"UPDATE {table} SET source = 'modified' WHERE ingestion_id = %s",
                (ingestion_id,),
            )

    # Verify row unchanged
    cur = db_conn.execute(
        f"SELECT source FROM {table} WHERE ingestion_id = %s", (ingestion_id,)
    )
    assert cur.fetchone()[0] == "test"


@pytest.mark.parametrize("table", list(RAW_TABLE_INSERTS.keys()))
def test_raw_table_rejects_delete(db_conn, table):
    """Raw tables reject DELETE via trg_block_raw_delete trigger."""
    cur = db_conn.execute(RAW_TABLE_INSERTS[table])
    ingestion_id = cur.fetchone()[0]

    with pytest.raises(psycopg.errors.RaiseException):
        with db_conn.transaction():
            db_conn.execute(
                f"DELETE FROM {table} WHERE ingestion_id = %s", (ingestion_id,)
            )

    # Verify row still exists
    cur = db_conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE ingestion_id = %s", (ingestion_id,)
    )
    assert cur.fetchone()[0] == 1
