from pathlib import Path
from typing import Any

import duckdb
import pytest

from bot.ingest import damodaran
from bot.ingest.damodaran import import_damodaran_from_files
from bot.reference.currencies import load_currency_table
from bot.screener.engine import _resolve_tax_rate as screener_tax_rate
from bot.storage.db import apply_schema, connect
from bot.valuator.assumptions import AssumptionSource, resolve_assumptions

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"

_FIXTURES_PRESENT = (FIXTURES / "wacc_sample.xls").exists() and (
    FIXTURES / "ctryprem_sample.xls"
).exists()

_SOFTWARE = "Software (System & Application)"

REPO_CURRENCIES = Path(__file__).resolve().parents[2] / "config" / "currencies.yaml"


def test_import_never_reads_the_preheader_scalar() -> None:
    assert not hasattr(damodaran, "parse_preheader_scalar")
    assert not hasattr(damodaran, "RISK_FREE_RATE_LABEL")


def _imported_conn() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    assert result.is_success(), result.error_message
    return conn


def _country_value(conn: duckdb.DuckDBPyConnection, column: str, country: str) -> Any:
    row = conn.execute(
        f"SELECT {column} FROM damodaran_country WHERE country = ?", [country]
    ).fetchone()
    assert row is not None, country
    return row[0]


def _seed_us_software_company(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry_damodaran, source) "
        "VALUES ('ACME', 'ACME Inc', 'United States', ?, 'test')",
        [_SOFTWARE],
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, currency, source) "
        "VALUES ('ACME', 2025, 'USD', 'test')"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7.",
)
def test_import_damodaran_from_files_populates_db():
    conn = connect(":memory:")
    apply_schema(conn)

    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )

    assert result.is_success()
    assert result.rows_affected > 0

    industry_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]
    country_count = conn.execute("SELECT COUNT(*) FROM damodaran_country").fetchone()[0]
    assert industry_count > 50
    assert country_count > 100

    refresh_rows = conn.execute(
        "SELECT source, status, rows_affected FROM refresh_log WHERE source = 'damodaran'"
    ).fetchall()
    assert len(refresh_rows) == 1
    assert refresh_rows[0][1] == "success"

    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not (FIXTURES / "wacc_sample.xls").exists(),
    reason="Damodaran fixtures not downloaded; run Task 7.",
)
def test_import_damodaran_is_idempotent():
    conn = connect(":memory:")
    apply_schema(conn)

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    first_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=2026,
    )
    second_count = conn.execute("SELECT COUNT(*) FROM damodaran_industry").fetchone()[0]

    assert first_count == second_count
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_import_fills_country_tax_rates_and_no_risk_free_column() -> None:
    conn = _imported_conn()

    assert _country_value(conn, "tax_rate", "United States") == pytest.approx(0.25)
    # #109: the US Treasury scalar is no longer broadcast into every country row;
    # the risk-free rate is keyed by valuation currency in config/currencies.yaml.
    columns = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'damodaran_country'"
        ).fetchall()
    }
    assert "risk_free_rate" not in columns
    assert _country_value(conn, "tax_rate", "Australia") == pytest.approx(0.30)
    assert _country_value(conn, "tax_rate", "Bahamas") == pytest.approx(0.0)

    counts = conn.execute("SELECT COUNT(*), COUNT(tax_rate) FROM damodaran_country").fetchone()
    assert counts is not None
    total, with_tax = counts
    # Aggregate rows such as "Frontier Markets (no sovereign ratings)" have no rate.
    assert with_tax / total >= 0.95
    out_of_range = conn.execute(
        "SELECT country, tax_rate FROM damodaran_country "
        "WHERE tax_rate IS NOT NULL AND (tax_rate < 0 OR tax_rate > 1)"
    ).fetchall()
    assert out_of_range == []
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_terminal_growth_uses_the_currency_file_usd_rate() -> None:
    """The US pin moved from the importer (#51) to the currency file (#109).

    The file's USD pair is (rfr 0.0395, GDP 0.04): the same 3.95% the importer
    used to read from wacc.xls, so min() still picks the rate.
    """
    conn = _imported_conn()
    _seed_us_software_company(conn)

    growth = resolve_assumptions(
        "ACME", conn, currencies=load_currency_table(REPO_CURRENCIES)
    ).terminal_growth

    assert growth.value == pytest.approx(0.0395)
    assert growth.source is AssumptionSource.RULE_BASED
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_screener_reads_the_imported_us_tax_rate() -> None:
    conn = _imported_conn()
    assert screener_tax_rate(conn, "United States") == pytest.approx(0.25)
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _FIXTURES_PRESENT, reason="Damodaran fixtures absent")
def test_valuator_falls_back_to_the_imported_country_tax_rate() -> None:
    conn = _imported_conn()
    _seed_us_software_company(conn)
    # Every fixture industry row carries a tax rate; blank one to reach the
    # country step of manual -> sector -> country -> default.
    conn.execute("UPDATE damodaran_industry SET tax_rate = NULL WHERE industry = ?", [_SOFTWARE])

    tax = resolve_assumptions("ACME", conn).tax_rate

    assert tax.value == pytest.approx(0.25)
    assert tax.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    conn.close()
