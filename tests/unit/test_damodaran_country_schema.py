"""``damodaran_country`` carries no risk-free rate (#109, ADR 0005 §4).

The rate is keyed by valuation currency in ``config/currencies.yaml``; the
schema drops the column, including from a database created before #109.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from bot.storage.db import apply_schema, connect

ADR_0005 = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "adr"
    / "0005-currency-handling-and-valuation-currency.md"
)


def _columns(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'damodaran_country'"
        ).fetchall()
    }


def test_damodaran_country_has_no_risk_free_rate_column() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    assert "risk_free_rate" not in _columns(conn)
    assert {"country", "year", "erp", "tax_rate", "region"} <= _columns(conn)


def test_apply_schema_drops_legacy_risk_free_rate_column() -> None:
    conn = connect(":memory:")
    conn.execute(
        "CREATE TABLE damodaran_country (country VARCHAR NOT NULL, year INTEGER NOT NULL, "
        "erp DOUBLE, country_risk_premium DOUBLE, risk_free_rate DOUBLE, tax_rate DOUBLE, "
        "rating VARCHAR, region VARCHAR, PRIMARY KEY (country, year))"
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, risk_free_rate, tax_rate) "
        "VALUES ('United States', 2026, 0.0395, 0.25)"
    )
    apply_schema(conn)
    apply_schema(conn)  # idempotent once the column is gone
    assert "risk_free_rate" not in _columns(conn)
    assert conn.execute("SELECT tax_rate FROM damodaran_country").fetchall() == [(0.25,)]


def test_adr_0005_section_4_is_implemented() -> None:
    status = ADR_0005.read_text().split("## Context", 1)[0]
    assert "§4" in status
    assert "Implemented" in status
