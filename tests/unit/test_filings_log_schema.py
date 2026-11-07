"""``filings_log`` carries the 8-K item numbers (#275), including on a database created before it."""

from __future__ import annotations

import duckdb

from bot.storage.db import apply_schema, connect


def _columns(conn: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'filings_log' ORDER BY ordinal_position"
        ).fetchall()
    ]


def test_filings_log_has_items_column() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    columns = _columns(conn)
    assert columns.index("items") == columns.index("accession_number") + 1


def test_apply_schema_adds_items_to_a_legacy_filings_log() -> None:
    conn = connect(":memory:")
    # The CREATE TABLE as it stood before #275.
    conn.execute(
        "CREATE TABLE filings_log (ticker VARCHAR NOT NULL, filing_type VARCHAR NOT NULL, "
        "filing_date DATE NOT NULL, accession_number VARCHAR, source VARCHAR NOT NULL, "
        "fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (ticker, filing_type, filing_date, source))"
    )
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, accession_number, source) "
        "VALUES ('AAPL', '10-K', DATE '2025-11-01', '0000320193-25-000106', 'edgar_tiingo')"
    )
    apply_schema(conn)
    apply_schema(conn)  # idempotent once the column exists
    assert "items" in _columns(conn)
    assert conn.execute(
        "SELECT ticker, filing_type, accession_number, items FROM filings_log"
    ).fetchall() == [("AAPL", "10-K", "0000320193-25-000106", None)]
