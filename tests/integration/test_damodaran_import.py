from pathlib import Path
from typing import Any

import duckdb
import pytest

from bot.ingest.damodaran import import_damodaran_from_files
from bot.screener.engine import _resolve_tax_rate as screener_tax_rate
from bot.storage.db import apply_schema, connect
from bot.valuator.assumptions import AssumptionSource, resolve_assumptions

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"

_FIXTURES_PRESENT = (FIXTURES / "wacc_sample.xls").exists() and (
    FIXTURES / "ctryprem_sample.xls"
).exists()

_SOFTWARE = "Software (System & Application)"


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
def test_import_fills_country_tax_and_risk_free_rates() -> None:
    conn = _imported_conn()

    assert _country_value(conn, "tax_rate", "United States") == pytest.approx(0.25)
    assert _country_value(conn, "risk_free_rate", "United States") == pytest.approx(0.0395)
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
def test_terminal_growth_is_capped_by_the_imported_risk_free_rate() -> None:
    conn = _imported_conn()
    _seed_us_software_company(conn)
    gdp_nominal = 0.04  # above the imported 0.0395, so min() must pick the rate

    growth = resolve_assumptions("ACME", conn, gdp_nominal=gdp_nominal).terminal_growth

    assert growth.value == pytest.approx(min(0.0395, gdp_nominal))
    assert growth.value != pytest.approx(gdp_nominal)
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
