"""Unit tests for assumptions resolution with source tracking (issue #12 / M4.2).

Spec §7.3: the six critical DCF assumptions, each carrying its provenance
(``source ∈ {manual, analyst_consensus, sector_default_damodaran, rule_based,
historical_average}``). The resolution order is:

1. Manual override from ``config/assumptions/<TICKER>.yaml`` if present
2. Analyst consensus (FMP, M2 — for the M1 universe, fall back to historical)
3. Sector default from ``damodaran_industry`` / ``damodaran_country``
4. Rule-based (e.g. ``terminal_growth = min(risk_free_rate, gdp_nominal)``)

These tests exercise each branch in isolation against an in-memory DuckDB and a
temporary override file, so resolution stays a pure function of (ticker, conn,
override_path).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from bot.storage.db import apply_schema, connect
from bot.valuator.assumptions import (
    Assumptions,
    AssumptionSource,
    Sourced,
    resolve_assumptions,
)
from bot.valuator.story_types import StoryType

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

GDP_NOMINAL_US = 0.04  # rule-based terminal-growth cap input (US nominal GDP).


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    connection = connect(":memory:")
    apply_schema(connection)
    return connection


def _seed_company(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str = "ACME",
    country: str = "United States",
    industry_damodaran: str = "Software",
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Inc", country, industry_damodaran, "test"],
    )


def _seed_industry(
    conn: duckdb.DuckDBPyConnection,
    *,
    industry: str = "Software",
    region: str = "US",
    year: int = 2024,
    wacc: float | None = 0.09,
    cost_of_equity: float | None = 0.10,
    cost_of_debt: float | None = 0.04,
    op_margin: float | None = 0.18,
    sales_to_capital: float | None = 2.5,
    tax_rate: float | None = 0.21,
    debt_to_equity: float | None = 0.25,
) -> None:
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, op_margin, "
        " sales_to_capital, tax_rate, debt_to_equity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            industry,
            region,
            year,
            wacc,
            cost_of_equity,
            cost_of_debt,
            op_margin,
            sales_to_capital,
            tax_rate,
            debt_to_equity,
        ],
    )


def _seed_country(
    conn: duckdb.DuckDBPyConnection,
    *,
    country: str = "United States",
    region: str = "US",
    year: int = 2024,
    risk_free_rate: float | None = 0.03,
    erp: float | None = 0.05,
    tax_rate: float | None = 0.21,
) -> None:
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, risk_free_rate, erp, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [country, year, risk_free_rate, erp, tax_rate, region],
    )


def _seed_financials(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str = "ACME",
    rows: tuple[tuple[int, float, float], ...] = (),
) -> None:
    """rows: (fiscal_year, revenue, ebit)."""
    for fiscal_year, revenue, ebit in rows:
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, source) VALUES (?, ?, ?, ?, ?)",
            [ticker, fiscal_year, revenue, ebit, "test"],
        )


def _seed_full_sector(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn)
    _seed_industry(conn)
    _seed_country(conn)


# --------------------------------------------------------------------------- #
# Sector / rule-based defaults                                                 #
# --------------------------------------------------------------------------- #


def test_returns_assumptions_with_sourced_fields(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert isinstance(result, Assumptions)
    for sourced in (
        result.revenue_growth,
        result.operating_margin,
        result.sales_to_capital,
        result.wacc,
        result.terminal_growth,
        result.probability_of_bankruptcy,
    ):
        assert isinstance(sourced, Sourced)
        assert isinstance(sourced.source, AssumptionSource)


def test_operating_margin_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.operating_margin.value == pytest.approx(0.18)
    assert result.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_sales_to_capital_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.sales_to_capital.value == pytest.approx(2.5)
    assert result.sales_to_capital.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_wacc_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.wacc.value == pytest.approx(0.09)
    assert result.wacc.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_probability_of_bankruptcy_defaults_to_zero_rule_based(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.probability_of_bankruptcy.value == pytest.approx(0.0)
    assert result.probability_of_bankruptcy.source is AssumptionSource.RULE_BASED


# --------------------------------------------------------------------------- #
# Terminal growth — rule-based cap (terminal_growth = min(rfr, gdp))           #
# --------------------------------------------------------------------------- #


def test_terminal_growth_capped_by_risk_free_rate(conn: duckdb.DuckDBPyConnection) -> None:
    """rfr (0.03) < gdp (0.04) → terminal_growth = rfr."""
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    assert result.terminal_growth.value == pytest.approx(0.03)
    assert result.terminal_growth.source is AssumptionSource.RULE_BASED


def test_terminal_growth_capped_by_gdp_when_rfr_higher(conn: duckdb.DuckDBPyConnection) -> None:
    """rfr (0.06) > gdp (0.04) → terminal_growth = gdp."""
    _seed_company(conn)
    _seed_industry(conn)
    _seed_country(conn, risk_free_rate=0.06)
    result = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    assert result.terminal_growth.value == pytest.approx(0.04)
    assert result.terminal_growth.source is AssumptionSource.RULE_BASED


# --------------------------------------------------------------------------- #
# Revenue growth — historical-average fallback for the M1 universe             #
# --------------------------------------------------------------------------- #


def test_revenue_growth_uses_historical_average_when_no_consensus(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    # Revenue 100 -> 110 -> 121: two YoY growths of 10% each → average 10%.
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 110.0, 20.0), (2024, 121.0, 22.0)),
    )
    result = resolve_assumptions("ACME", conn)
    assert result.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE
    assert all(g == pytest.approx(0.10) for g in result.revenue_growth.value)


def test_revenue_growth_without_history_falls_back_to_rule_based_gdp(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """No financial history → rule-based growth path anchored on nominal GDP."""
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    assert result.revenue_growth.source is AssumptionSource.RULE_BASED
    assert all(g == pytest.approx(GDP_NOMINAL_US) for g in result.revenue_growth.value)


# --------------------------------------------------------------------------- #
# Manual override wins                                                         #
# --------------------------------------------------------------------------- #


def _write_override(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ACME.yaml"
    path.write_text(body)
    return path


def test_manual_override_wins_for_every_field(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    override = _write_override(
        tmp_path,
        "\n".join(
            [
                "story_type: high-growth",
                "revenue_growth: [0.20, 0.18, 0.15, 0.12, 0.10]",
                "operating_margin: 0.30",
                "sales_to_capital: 3.0",
                "wacc: 0.08",
                "terminal_growth: 0.025",
                "probability_of_bankruptcy: 0.10",
                "notes: 'consensus looked biased'",
            ]
        ),
    )
    result = resolve_assumptions("ACME", conn, override_path=override)

    assert result.operating_margin.value == pytest.approx(0.30)
    assert result.operating_margin.source is AssumptionSource.MANUAL
    assert result.sales_to_capital.value == pytest.approx(3.0)
    assert result.sales_to_capital.source is AssumptionSource.MANUAL
    assert result.wacc.value == pytest.approx(0.08)
    assert result.wacc.source is AssumptionSource.MANUAL
    assert result.terminal_growth.value == pytest.approx(0.025)
    assert result.terminal_growth.source is AssumptionSource.MANUAL
    assert result.probability_of_bankruptcy.value == pytest.approx(0.10)
    assert result.probability_of_bankruptcy.source is AssumptionSource.MANUAL
    assert result.revenue_growth.value == (0.20, 0.18, 0.15, 0.12, 0.10)
    assert result.revenue_growth.source is AssumptionSource.MANUAL


def test_manual_override_is_partial_other_fields_keep_defaults(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """An override that sets only one field leaves the rest on their defaults."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "operating_margin: 0.40\n")
    result = resolve_assumptions("ACME", conn, override_path=override)

    assert result.operating_margin.value == pytest.approx(0.40)
    assert result.operating_margin.source is AssumptionSource.MANUAL
    # Untouched field keeps the sector default.
    assert result.sales_to_capital.value == pytest.approx(2.5)
    assert result.sales_to_capital.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_override_path_absent_is_ignored(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """A non-existent override path resolves entirely from defaults."""
    _seed_full_sector(conn)
    missing = tmp_path / "NOPE.yaml"
    result = resolve_assumptions("ACME", conn, override_path=missing)
    assert result.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_story_type_from_override_is_surfaced(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "story_type: distressed\nnotes: 'see 10-K'\n")
    result = resolve_assumptions("ACME", conn, override_path=override)
    assert result.story_type == "distressed"
    assert result.notes == "see 10-K"


def test_auto_story_type_is_used_when_no_override(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The classifier's verdict is surfaced when the YAML has no story_type."""
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn, auto_story_type=StoryType.HIGH_GROWTH)
    assert result.story_type == "high-growth"


def test_manual_story_type_override_beats_auto_classification(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """A YAML ``story_type`` wins over the classifier (spec §7.6 override hook)."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "story_type: distressed\n")
    result = resolve_assumptions(
        "ACME", conn, override_path=override, auto_story_type=StoryType.HIGH_GROWTH
    )
    assert result.story_type == "distressed"


def test_story_type_is_none_without_override_or_auto(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.story_type is None


# --------------------------------------------------------------------------- #
# Missing-data behaviour                                                       #
# --------------------------------------------------------------------------- #


def test_unknown_company_raises(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(LookupError):
        resolve_assumptions("GHOST", conn)


def test_missing_sector_row_leaves_field_unresolved(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """A company whose industry has no Damodaran row still resolves, with the
    sector-sourced fields marked unavailable (value None) rather than crashing."""
    _seed_company(conn, industry_damodaran="Obscure")
    _seed_country(conn)
    result = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    assert result.operating_margin.value is None
    assert result.sales_to_capital.value is None
    # Country-derived rule-based terminal growth still resolves.
    assert result.terminal_growth.value == pytest.approx(0.03)


def test_to_dcf_assumptions_roundtrip(conn: duckdb.DuckDBPyConnection) -> None:
    """The resolved bundle converts into the pure dcf.Assumptions input."""
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 110.0, 20.0), (2024, 121.0, 22.0)),
    )
    result = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    dcf_assumptions = result.to_dcf_assumptions()
    assert dcf_assumptions.terminal_growth == pytest.approx(0.03)
    assert dcf_assumptions.operating_margin == tuple(
        [0.18] * len(result.revenue_growth.value)
    )
    assert len(dcf_assumptions.revenue_growth) == len(result.revenue_growth.value)
