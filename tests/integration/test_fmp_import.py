"""Integration tests for the high-level FMP fundamentals importer (M2.3).

``import_company_from_fmp`` mirrors ``import_company_from_sec``: it fetches the
profile + income / balance / cash-flow statements (annual and quarterly), parses
them with the pure M2.2 parser, and upserts a single ticker atomically.

Network is replayed from VCR cassettes in ``tests/fixtures/cassettes/fmp/``. The
cassettes are SYNTHETIC (hand-authored, fabricated-but-realistic FMP JSON) so the
suite runs deterministically offline with no live calls. They MUST be re-recorded
against the live FMP API with a real BOT_FMP_API_KEY before production use.
"""

from __future__ import annotations

import pytest

from bot.ingest.fmp import import_company_from_fmp
from bot.storage.db import apply_schema, connect

API_KEY = "test-fmp-key"


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fmp")


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": [("apikey", "SCRUBBED")],
        "record_mode": "once",
    }


@pytest.mark.integration
@pytest.mark.vcr
def test_import_company_from_fmp_us_populates_db() -> None:
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_company_from_fmp(conn, ticker="AAPL", api_key=API_KEY)

    assert result.is_success()
    assert result.source == "fmp"
    assert result.rows_affected > 0

    companies = conn.execute(
        "SELECT ticker, name, country, currency, source "
        "FROM companies WHERE ticker = 'AAPL'"
    ).fetchall()
    assert len(companies) == 1
    assert companies[0] == ("AAPL", "Apple Inc.", "US", "USD", "fmp")

    annual = conn.execute(
        "SELECT fiscal_year, revenue, ebitda, free_cashflow, currency, is_restated "
        "FROM financials_annual WHERE ticker = 'AAPL' ORDER BY fiscal_year"
    ).fetchall()
    assert len(annual) >= 2
    latest = annual[-1]
    assert latest[1] is not None  # revenue populated
    assert latest[2] is not None  # ebitda populated
    assert latest[3] is not None  # free_cashflow populated
    assert latest[4] == "USD"

    # At least one fiscal year is flagged restated (a year reported twice).
    assert any(row[5] for row in annual)

    quarterly = conn.execute(
        "SELECT COUNT(*) FROM financials_quarterly WHERE ticker = 'AAPL'"
    ).fetchone()
    assert quarterly is not None
    assert quarterly[0] >= 1

    refresh = conn.execute(
        "SELECT status FROM refresh_log WHERE source = 'fmp'"
    ).fetchall()
    assert refresh[0][0] == "success"

    conn.close()


@pytest.mark.integration
@pytest.mark.vcr
def test_import_company_from_fmp_non_us_has_local_currency() -> None:
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_company_from_fmp(conn, ticker="NESN.SW", api_key=API_KEY)

    assert result.is_success()

    company = conn.execute(
        "SELECT name, country, currency FROM companies WHERE ticker = 'NESN.SW'"
    ).fetchone()
    assert company is not None
    name, country, currency = company
    assert name == "Nestlé S.A."
    # Non-US / non-USD: this is the whole point of FMP over SEC EDGAR.
    assert country == "CH"
    assert country != "US"
    assert currency == "CHF"
    assert currency != "USD"

    fin_currency = conn.execute(
        "SELECT DISTINCT currency FROM financials_annual WHERE ticker = 'NESN.SW'"
    ).fetchall()
    assert fin_currency == [("CHF",)]

    conn.close()
