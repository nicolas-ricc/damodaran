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
import pytest
from structlog.testing import capture_logs

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
# #123 — count of annual periods still without revenue
# ---------------------------------------------------------------------------


def _annual_fact(start: str, end: str, val: float) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": "0000320193-25-000001",
        "fy": 2025,
        "fp": "FY",
        "form": "10-K",
        "filed": "2025-11-01",
    }


def test_import_company_from_sec_reports_null_revenue_count() -> None:
    facts: dict[str, Any] = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_annual_fact("2024-01-01", "2024-12-31", 1e9)]}
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            _annual_fact("2024-01-01", "2024-12-31", 1e8),
                            _annual_fact("2025-01-01", "2025-12-31", 2e8),
                        ]
                    }
                },
            }
        },
    }
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    with (
        patch("bot.ingest.sec_edgar.SecEdgarClient.lookup_cik", return_value="0000320193"),
        patch("bot.ingest.sec_edgar.SecEdgarClient.fetch_company_facts", return_value=facts),
        capture_logs() as logs,
    ):
        result = import_company_from_sec(conn, ticker="AAPL", user_agent="Test test@example.com")

    assert result.is_success()
    assert result.details["annual_revenue_null"] == 1
    events = [e for e in logs if e["event"] == "ingest.annual_revenue_null"]
    assert len(events) == 1
    assert events[0]["annual_revenue_null"] == 1
    assert events[0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# #124 — share-count rescales are counted in the import log
# ---------------------------------------------------------------------------


def _mcd_shares_facts() -> dict[str, Any]:
    years = {2019: 750_100_000.0, 2020: 741_300_000.0, 2021: 751_800_000.0, 2022: 732.3, 2023: 721.9}

    def entry(year: int, val: float) -> dict[str, Any]:
        return {
            "start": f"{year}-01-01",
            "end": f"{year}-12-31",
            "val": val,
            "accn": f"0000063908-{year + 1}-000010",
            "fy": year,
            "fp": "FY",
            "form": "10-K",
            "filed": f"{year + 1}-02-20",
        }

    return {
        "cik": 63908,
        "entityName": "McDonald's Corp",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [entry(y, 25e9) for y in years]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {"shares": [entry(y, v) for y, v in years.items()]}
                },
            }
        },
    }


def test_import_company_from_sec_records_shares_rescaled() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    with (
        patch("bot.ingest.sec_edgar.SecEdgarClient.lookup_cik", return_value="0000063908"),
        patch(
            "bot.ingest.sec_edgar.SecEdgarClient.fetch_company_facts",
            return_value=_mcd_shares_facts(),
        ),
    ):
        result = import_company_from_sec(conn, ticker="MCD", user_agent="Test t@example.com")

    assert result.is_success(), result.error_message
    assert result.details["shares_rescaled"] == 2
    stored = conn.execute(
        "SELECT fiscal_year, shares_diluted FROM financials_annual "
        "WHERE ticker = 'MCD' AND fiscal_year >= 2022 ORDER BY fiscal_year"
    ).fetchall()
    assert stored == [(2022, pytest.approx(732_300_000)), (2023, pytest.approx(721_900_000))]
