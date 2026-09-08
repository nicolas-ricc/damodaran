"""Unit tests for import_company_from_sec (Block 3 hardening).

Covers:
- Fix 1: if the shared _log_refresh raises, import_company_from_sec still returns
  the IngestResult instead of propagating the exception.
- Task 3: upsert_company merges instead of wiping unrelated columns.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import duckdb

from bot.ingest.base import IngestResult
from bot.ingest.sec_edgar import import_company_from_sec, upsert_company
from bot.storage.db import apply_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_FACTS: dict[str, Any] = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {"us-gaap": {}},
}


def _make_mock_conn() -> MagicMock:
    """Return a mock DuckDB connection that accepts execute calls."""
    conn = MagicMock()
    conn.execute.return_value = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# Fix 1 — _log_refresh failure must not crash the importer
# ---------------------------------------------------------------------------


def test_import_company_returns_result_even_when_log_insert_fails() -> None:
    """If the shared _log_refresh raises, import_company_from_sec must swallow the
    exception and still return a valid IngestResult (success or error)."""
    conn = _make_mock_conn()

    with (
        patch(
            "bot.ingest.base._log_refresh",
            side_effect=RuntimeError("DB closed — cannot insert refresh log"),
        ),
        patch(
            "bot.ingest.sec_edgar.SecEdgarClient.lookup_cik",
            return_value="0000320193",
        ),
        patch(
            "bot.ingest.sec_edgar.SecEdgarClient.fetch_company_facts",
            return_value=MINIMAL_FACTS,
        ),
    ):
        result = import_company_from_sec(
            conn,
            ticker="AAPL",
            user_agent="Test User test@example.com",
        )

    assert isinstance(result, IngestResult), (
        "import_company_from_sec must return an IngestResult even when _log_refresh_sec raises"
    )
    assert result.source == "sec_edgar"
    assert result.status in {"success", "error"}


# ---------------------------------------------------------------------------
# Task 3 — upsert_company merge semantics
# ---------------------------------------------------------------------------


def test_upsert_company_preserves_columns_the_new_row_does_not_carry() -> None:
    """upsert_company merges: a column absent or None in the new row retains its
    existing DB value. This ensures a SEC upsert (which lacks industry columns)
    doesn't wipe the industry_damodaran value written by FMP."""
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, currency, source) "
        "VALUES ('AAPL', 'Apple Inc.', 'US', 'Consumer Electronics', 'Computers/Peripherals', 'USD', 'fmp')"
    )
    # SEC row doesn't bring industry, industry_damodaran, or currency.
    upsert_company(conn, {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "source": "sec_edgar"})
    row = conn.execute(
        "SELECT industry_damodaran, industry, currency, cik, source FROM companies WHERE ticker = 'AAPL'"
    ).fetchone()
    assert row == ("Computers/Peripherals", "Consumer Electronics", "USD", "0000320193", "sec_edgar")
