import re
from importlib import resources
from typing import Any

import duckdb
import pytest

from bot.ingest.fmp import parse_fmp_fundamentals
from bot.ingest.sec_edgar import (
    parse_company_facts,
    upsert_financials_annual,
    upsert_financials_quarterly,
)
from bot.storage.db import _count_create_tables, apply_schema, connect, schema_table_count

# ``financials_annual`` as schema.sql created it before #278 (no ``acquisitions``).
_LEGACY_FINANCIALS_ANNUAL_DDL = """
    CREATE TABLE financials_annual (
        ticker          VARCHAR NOT NULL,
        fiscal_year     INTEGER NOT NULL,
        period_end_date DATE,
        currency        VARCHAR,
        revenue         DOUBLE,
        cogs            DOUBLE,
        gross_profit    DOUBLE,
        operating_expenses DOUBLE,
        ebit            DOUBLE,
        ebitda          DOUBLE,
        interest_expense DOUBLE,
        tax_expense     DOUBLE,
        net_income      DOUBLE,
        total_assets    DOUBLE,
        total_debt      DOUBLE,
        cash            DOUBLE,
        total_equity    DOUBLE,
        goodwill        DOUBLE,
        working_capital DOUBLE,
        capex           DOUBLE,
        depreciation    DOUBLE,
        operating_cashflow DOUBLE,
        free_cashflow   DOUBLE,
        dividends_paid  DOUBLE,
        shares_diluted  DOUBLE,
        is_restated     BOOLEAN DEFAULT FALSE,
        source          VARCHAR NOT NULL,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, fiscal_year, is_restated)
    )
"""


def test_connect_creates_file(tmp_path):
    db_file = tmp_path / "x.duckdb"
    conn = connect(db_file)
    assert db_file.exists()
    result = conn.execute("SELECT 1 AS x").fetchone()
    assert result == (1,)
    conn.close()


def test_apply_schema_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    expected = {
        "damodaran_industry",
        "damodaran_country",
        "companies",
        "financials_annual",
        "financials_quarterly",
        "filings_log",
        "refresh_log",
        "screener_candidates",
        "currencies",
    }
    assert expected.issubset(tables)
    conn.close()


def test_screener_candidates_table_has_expected_columns(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = 'screener_candidates'"
        ).fetchall()
    }
    expected = {
        "run_id",
        "preset",
        "ticker",
        "rank",
        "score",
        "value_score",
        "quality_score",
        "growth_score",
        "mos_score",
        "passed_gates",
        "failed_gates",
        "created_at",
    }
    assert expected.issubset(columns)
    conn.close()


def test_screener_candidates_round_trips_a_row(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        """
        INSERT INTO screener_candidates
            (run_id, preset, ticker, rank, score,
             value_score, quality_score, growth_score, mos_score,
             passed_gates, failed_gates)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "run-1",
            "damodaran_value",
            "AAPL",
            1,
            0.87,
            0.9,
            0.8,
            0.7,
            0.6,
            ["market_cap", "interest_coverage"],
            ["roic_vs_wacc"],
        ],
    )
    row = conn.execute(
        "SELECT preset, ticker, rank, passed_gates, failed_gates "
        "FROM screener_candidates WHERE run_id = ?",
        ["run-1"],
    ).fetchone()
    assert row is not None
    preset, ticker, rank, passed, failed = row
    assert (preset, ticker, rank) == ("damodaran_value", "AAPL", 1)
    assert list(passed) == ["market_cap", "interest_coverage"]
    assert list(failed) == ["roic_vs_wacc"]
    conn.close()


def test_apply_schema_is_idempotent(tmp_path):
    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    apply_schema(conn)  # must not raise
    conn.close()


def test_connect_in_memory():
    conn = connect(":memory:")
    apply_schema(conn)
    result = conn.execute("SELECT COUNT(*) FROM companies").fetchone()
    assert result == (0,)
    conn.close()


def test_count_create_tables_ignores_case_spacing_and_comments() -> None:
    sql = """
    -- CREATE TABLE IF NOT EXISTS commented_out (x INT);
    create table   if   not   exists  a (x INT);
    CREATE TABLE b (x INT);
    CREATE INDEX ix ON b (x);
    """
    assert _count_create_tables(sql) == 2


def test_schema_table_count_matches_the_shipped_schema() -> None:
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    expected = len(re.findall(r"(?im)^\s*create\s+table\b", sql))
    assert schema_table_count() == expected == 16


def _financials_annual_columns(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'financials_annual'"
        ).fetchall()
    }


def _db(kind: str) -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    if kind == "migrated":
        conn.execute(_LEGACY_FINANCIALS_ANNUAL_DDL)
    apply_schema(conn)
    return conn


def test_financials_annual_has_acquisitions_column() -> None:
    conn = _db("fresh")
    assert _financials_annual_columns(conn).get("acquisitions") == "DOUBLE"


def test_apply_schema_adds_acquisitions_to_a_legacy_financials_annual() -> None:
    conn = connect(":memory:")
    conn.execute(_LEGACY_FINANCIALS_ANNUAL_DDL)
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, source, capex) "
        "VALUES ('AAPL', 2024, 'sec_edgar', 1.0)"
    )
    apply_schema(conn)
    apply_schema(conn)  # idempotent once the column exists
    assert _financials_annual_columns(conn) == _financials_annual_columns(_db("fresh"))
    assert conn.execute(
        "SELECT ticker, fiscal_year, capex, acquisitions FROM financials_annual"
    ).fetchall() == [("AAPL", 2024, 1.0, None)]


def _edgar_fact(end: str, start: str, val: float, form: str = "10-K") -> dict[str, Any]:
    fp = "FY" if form == "10-K" else "Q1"
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": "0000063908-26-000010",
        "fy": int(end[:4]),
        "fp": fp,
        "form": form,
        "filed": f"{int(end[:4]) + 1}-02-20" if form == "10-K" else end[:4] + "-05-01",
    }


def _edgar_facts(concepts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "cik": 63908,
        "entityName": "McDonald's Corp",
        "facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in concepts.items()}},
    }


@pytest.mark.parametrize("kind", ["fresh", "migrated"])
def test_edgar_acquisitions_round_trip(kind: str) -> None:
    facts = _edgar_facts(
        {
            "Revenues": [
                _edgar_fact("2024-12-31", "2024-01-01", 25_920_000_000),
                _edgar_fact("2025-12-31", "2025-01-01", 26_885_000_000),
            ],
            "PaymentsToAcquireBusinessesNetOfCashAcquired": [
                _edgar_fact("2025-12-31", "2025-01-01", 1_500_000_000)
            ],
        }
    )
    conn = _db(kind)
    upsert_financials_annual(conn, parse_company_facts("MCD", facts).annual)
    assert conn.execute(
        "SELECT fiscal_year, acquisitions FROM financials_annual ORDER BY fiscal_year"
    ).fetchall() == [(2024, None), (2025, 1_500_000_000.0)]


def test_a_10q_acquisitions_fact_never_reaches_financials_quarterly() -> None:
    facts = _edgar_facts(
        {
            "Revenues": [_edgar_fact("2025-03-31", "2025-01-01", 6_000_000_000, form="10-Q")],
            "PaymentsToAcquireBusinessesNetOfCashAcquired": [
                _edgar_fact("2025-03-31", "2025-01-01", 400_000_000, form="10-Q")
            ],
        }
    )
    conn = _db("fresh")
    assert upsert_financials_quarterly(conn, parse_company_facts("MCD", facts).quarterly) == 1
    quarterly_cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'financials_quarterly'"
        ).fetchall()
    }
    assert "acquisitions" not in quarterly_cols


@pytest.mark.parametrize("kind", ["fresh", "migrated"])
def test_fmp_acquisitions_round_trip(kind: str) -> None:
    cashflow = [
        {"date": "2023-12-31", "calendarYear": "2023", "period": "FY", "acquisitionsNet": -500}
    ]
    conn = _db(kind)
    upsert_financials_annual(conn, parse_fmp_fundamentals("AAPL", [], [], cashflow).annual)
    assert conn.execute("SELECT acquisitions FROM financials_annual").fetchall() == [(500.0,)]
