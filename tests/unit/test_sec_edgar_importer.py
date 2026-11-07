"""Unit tests for the SEC EDGAR upserts and the importer's log hardening.

Covers:
- Fix 1: if the shared _log_refresh raises, universe.import_company still returns
  the IngestResult instead of propagating the exception.
- Task 3: upsert_company merges instead of wiping unrelated columns.
- #28: upsert_filings keeps the first ingestion time.
- #58: import_company_from_sec is gone; bot show --fetch goes through the provider port.
"""

from __future__ import annotations

from unittest.mock import patch

import duckdb

from bot.ingest import sec_edgar
from bot.ingest.base import IngestResult
from bot.ingest.edgar_base import EdgarPricedProvider
from bot.ingest.provider import CompanyInfo
from bot.ingest.sec_edgar import upsert_company
from bot.ingest.universe import import_company
from bot.storage.db import apply_schema
from tests.fake_provider import FakeProvider

# ---------------------------------------------------------------------------
# Fix 1 — _log_refresh failure must not crash the importer
# ---------------------------------------------------------------------------


def test_import_company_returns_result_even_when_log_insert_fails() -> None:
    """If the shared _log_refresh raises, universe.import_company must swallow the
    exception and still return the IngestResult of the import itself."""
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    provider = FakeProvider(
        companies={
            "AAPL": CompanyInfo(
                ticker="AAPL",
                name="Apple Inc.",
                exchange=None,
                exchange_short_name=None,
                country="US",
                currency="USD",
                sector=None,
                industry=None,
                is_actively_trading=True,
                ipo_date=None,
            )
        }
    )

    with patch(
        "bot.ingest.base._log_refresh",
        side_effect=RuntimeError("DB closed — cannot insert refresh log"),
    ):
        result = import_company(conn, ticker="AAPL", provider=provider)

    assert isinstance(result, IngestResult), (
        "import_company must return an IngestResult even when _log_refresh raises"
    )
    assert result.source == "fake"
    assert result.status == "success"


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


# ---------------------------------------------------------------------------
# upsert_filings keeps the original ingestion time (#28)
# ---------------------------------------------------------------------------


def test_upsert_filings_preserves_fetched_at() -> None:
    from datetime import date, datetime

    from bot.ingest.sec_edgar import upsert_filings

    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    filing = {
        "ticker": "AAPL",
        "filing_type": "10-K",
        "filing_date": date(2026, 1, 30),
        "accession_number": "0001",
        "source": "sec-edgar",
    }
    upsert_filings(conn, [filing])
    first_seen = datetime(2026, 2, 1, 9, 0)
    conn.execute("UPDATE filings_log SET fetched_at = ?", [first_seen])

    assert upsert_filings(conn, [{**filing, "accession_number": "0002"}]) == 1

    rows = conn.execute("SELECT accession_number, fetched_at FROM filings_log").fetchall()
    assert rows == [("0002", first_seen)]


# ---------------------------------------------------------------------------
# #58 — the SEC-only importer is retired
# ---------------------------------------------------------------------------


def test_import_company_from_sec_no_longer_exists() -> None:
    assert not hasattr(sec_edgar, "import_company_from_sec")


def test_docstrings_no_longer_describe_show_fetch_as_sec_stamped() -> None:
    for doc in (upsert_company.__doc__, EdgarPricedProvider._restamp.__doc__):
        assert "show --fetch" not in " ".join((doc or "").split())
