"""Integration tests for import_company_from_fmp using VCR cassettes."""

from __future__ import annotations

import duckdb
import pytest

from bot.ingest.fmp import import_company_from_fmp
from bot.storage.db import apply_schema


@pytest.fixture  # type: ignore[misc]
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / "fmp")


@pytest.fixture  # type: ignore[misc]
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["apikey"],
        "record_mode": "none",
    }


@pytest.fixture  # type: ignore[misc]
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    return conn


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_import_company_from_fmp_aapl(db: duckdb.DuckDBPyConnection) -> None:
    result = import_company_from_fmp(db, "AAPL", api_key="test_key")

    assert result.status == "success"
    assert result.source == "fmp"
    assert result.rows_affected >= 3  # 1 company + ≥1 annual + ≥1 quarterly

    company = db.execute("SELECT * FROM companies WHERE ticker = 'AAPL'").fetchone()
    assert company is not None
    row = dict(zip([d[0] for d in db.description], company, strict=False))  # type: ignore[union-attr]
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
    assert row["currency"] == "USD"
    assert row["country"] == "US"
    assert row["exchange"] == "NASDAQ"
    assert row["cik"] == "0000320193"
    assert row["source"] == "fmp"

    annual = db.execute(
        "SELECT fiscal_year, currency, revenue, is_restated FROM financials_annual WHERE ticker = 'AAPL' ORDER BY fiscal_year"
    ).fetchall()
    assert len(annual) >= 2
    years = [r[0] for r in annual]
    assert 2022 in years
    assert 2023 in years
    # All rows have USD currency
    for r in annual:
        assert r[1] == "USD"

    quarterly = db.execute(
        "SELECT fiscal_year, fiscal_quarter, currency FROM financials_quarterly WHERE ticker = 'AAPL' ORDER BY fiscal_year, fiscal_quarter"
    ).fetchall()
    assert len(quarterly) >= 2
    for r in quarterly:
        assert r[2] == "USD"

    log = db.execute(
        "SELECT status, rows_affected FROM refresh_log WHERE source = 'fmp'"
    ).fetchone()
    assert log is not None
    assert log[0] == "success"


@pytest.mark.vcr  # type: ignore[misc]
@pytest.mark.integration
def test_import_company_from_fmp_nesn_sw(db: duckdb.DuckDBPyConnection) -> None:
    result = import_company_from_fmp(db, "NESN.SW", api_key="test_key")

    assert result.status == "success"
    assert result.source == "fmp"

    company = db.execute("SELECT * FROM companies WHERE ticker = 'NESN.SW'").fetchone()
    assert company is not None
    row = dict(zip([d[0] for d in db.description], company, strict=False))  # type: ignore[union-attr]
    assert row["ticker"] == "NESN.SW"
    assert row["currency"] == "CHF"
    assert row["currency"] != "USD"
    assert row["country"] == "CH"
    assert row["country"] != "US"
    assert row["exchange"] == "SIX"
    assert row["isin"] == "CH0012221716"
    assert row["cik"] is None  # non-US: no SEC CIK

    annual = db.execute(
        "SELECT fiscal_year, currency FROM financials_annual WHERE ticker = 'NESN.SW'"
    ).fetchall()
    assert len(annual) >= 1
    for r in annual:
        assert r[1] == "CHF"
        assert r[1] != "USD"

    quarterly = db.execute(
        "SELECT fiscal_year, fiscal_quarter, currency FROM financials_quarterly WHERE ticker = 'NESN.SW'"
    ).fetchall()
    assert len(quarterly) >= 1
    for r in quarterly:
        assert r[2] == "CHF"
        assert r[2] != "USD"
