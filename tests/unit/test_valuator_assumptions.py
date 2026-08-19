"""Unit tests for assumptions resolution with source tracking (issue #12 / M4.2).

Spec §7.3: the six critical DCF assumptions, each carrying its provenance
(``source ∈ {manual, sector_default_damodaran,
sector_default_damodaran_cross_region, rule_based, historical_average,
unresolved}``). ``analyst_consensus`` was removed: nothing ever emitted it.
The resolution order is:

1. Manual override from ``config/assumptions/<TICKER>.yaml`` if present
2. Analyst consensus (FMP, M2 — for the M1 universe, fall back to historical)
3. Sector default from ``damodaran_industry`` / ``damodaran_country``
4. Rule-based (e.g. ``terminal_growth = min(risk_free_rate, gdp_nominal)``)

These tests exercise each branch in isolation against an in-memory DuckDB and a
temporary override file, so resolution stays a pure function of (ticker, conn,
override_path).
"""

from __future__ import annotations

import itertools
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
        result.cost_of_equity,
        result.pretax_cost_of_debt,
        result.equity_weight,
        result.debt_weight,
        result.terminal_growth,
        result.probability_of_bankruptcy,
    ):
        assert isinstance(sourced, Sourced)
        assert isinstance(sourced.source, AssumptionSource)


def test_operating_margin_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.operating_margin.value == pytest.approx((0.18,) * 5)
    assert result.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_sales_to_capital_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.sales_to_capital.value == pytest.approx(2.5)
    assert result.sales_to_capital.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_wacc_components_use_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    # There is no resolved Assumptions.wacc (see module docstring): the DCF
    # computes WACC from these four sourced components instead.
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.cost_of_equity.value == pytest.approx(0.10)
    assert result.cost_of_equity.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    assert result.pretax_cost_of_debt.value == pytest.approx(0.04)
    assert result.pretax_cost_of_debt.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


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
                "terminal_growth: 0.025",
                "probability_of_bankruptcy: 0.10",
                "notes: 'consensus looked biased'",
            ]
        ),
    )
    result = resolve_assumptions("ACME", conn, override_path=override)

    assert result.operating_margin.value == pytest.approx((0.30,) * 5)
    assert result.operating_margin.source is AssumptionSource.MANUAL
    assert result.sales_to_capital.value == pytest.approx(3.0)
    assert result.sales_to_capital.source is AssumptionSource.MANUAL
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

    assert result.operating_margin.value == pytest.approx((0.40,) * 5)
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


def test_invalid_manual_story_type_warns_and_stays_non_branching(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """An unknown ``story_type`` typo (e.g. ``hi-growth``) must not silently
    disable branching without a signal: it should log a warning naming the
    invalid value and the valid ones, while still surfacing the bogus label
    in the report and behaving as non-branching (no story-pattern resolution).
    """
    from structlog.testing import capture_logs

    _seed_full_sector(conn)
    override = _write_override(tmp_path, "story_type: hi-growth\n")
    with capture_logs() as events:
        result = resolve_assumptions("ACME", conn, override_path=override)

    assert result.story_type == "hi-growth"
    warnings = [e for e in events if e.get("event") == "assumptions.story_type.invalid"]
    assert len(warnings) == 1
    assert warnings[0]["log_level"] == "warning"
    assert warnings[0]["story_type"] == "hi-growth"
    assert set(warnings[0]["valid_story_types"]) == {s.value for s in StoryType}

    # Non-branching: no story pattern is applied to revenue growth or margin.
    assert result.revenue_growth.source != AssumptionSource.STORY_PATTERN
    assert result.operating_margin.source != AssumptionSource.STORY_PATTERN


# --------------------------------------------------------------------------- #
# Story type drives the projection (spec §7.1)                                 #
# --------------------------------------------------------------------------- #


def test_high_growth_revenue_path_fades_from_history_to_gdp(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    # 100 -> 130 -> 169: two YoY growths of 30% each → historical average 30%.
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 130.0, 20.0), (2024, 169.0, 22.0)),
    )
    a = resolve_assumptions("ACME", conn, gdp_nominal=0.04, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source == AssumptionSource.STORY_PATTERN
    assert path[0] == pytest.approx(0.30, abs=0.01)
    assert path[-1] == pytest.approx(0.04, abs=1e-9)
    assert all(x >= y for x, y in itertools.pairwise(path))  # monotone descending


def test_high_growth_margin_ramps_from_company_to_sector(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    _seed_industry(conn, op_margin=0.20)
    _seed_country(conn)
    # Company's own margin is a flat 8% every year -> the latest is 0.08.
    _seed_financials(
        conn,
        rows=((2022, 100.0, 8.0), (2023, 110.0, 8.8), (2024, 121.0, 9.68)),
    )
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.operating_margin.value
    assert path is not None
    assert a.operating_margin.source == AssumptionSource.STORY_PATTERN
    assert path[0] == pytest.approx(0.08, abs=1e-9)
    assert path[-1] == pytest.approx(0.20, abs=1e-9)


def test_cyclical_margin_averages_the_cycle_not_the_current_year(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    _seed_industry(conn)
    _seed_country(conn)
    # Margin history [0.02, 0.18, 0.04, 0.16] -> average 0.10; current year is 0.16.
    _seed_financials(
        conn,
        rows=(
            (2021, 100.0, 2.0),
            (2022, 100.0, 18.0),
            (2023, 100.0, 4.0),
            (2024, 100.0, 16.0),
        ),
    )
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.CYCLICAL)
    assert a.operating_margin.value == (pytest.approx(0.10),) * 5
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE


def test_mature_stable_keeps_sector_margin_and_historical_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 110.0, 20.0), (2024, 121.0, 22.0)),
    )
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.MATURE_STABLE)
    assert a.operating_margin.source == AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    assert a.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE


def test_manual_override_beats_the_story_pattern(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 8.0), (2023, 110.0, 8.8), (2024, 121.0, 9.68)),
    )
    override = _write_override(
        tmp_path, "operating_margin: 0.25\nstory_type: high-growth\n"
    )
    a = resolve_assumptions(
        "ACME", conn, override_path=override, auto_story_type=StoryType.HIGH_GROWTH
    )
    assert a.operating_margin.value == (0.25,) * 5
    assert a.operating_margin.source == AssumptionSource.MANUAL


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
    assert result.operating_margin.source is AssumptionSource.UNRESOLVED
    assert result.sales_to_capital.value is None
    assert result.sales_to_capital.source is AssumptionSource.UNRESOLVED
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
    # tax_rate flows through as the Damodaran sector rate, not a 100% placeholder.
    assert dcf_assumptions.tax_rate == pytest.approx(0.21)


def test_tax_rate_uses_sector_default(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn)
    assert result.tax_rate.value == pytest.approx(0.21)
    assert result.tax_rate.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_tax_rate_manual_override_wins(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _seed_full_sector(conn)
    override = tmp_path / "ACME.yaml"
    override.write_text("tax_rate: 0.15\n")
    result = resolve_assumptions("ACME", conn, override_path=override)
    assert result.tax_rate.value == pytest.approx(0.15)
    assert result.tax_rate.source is AssumptionSource.MANUAL


def test_tax_rate_rule_based_default_when_no_data(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn)  # company only, no sector/country tax rate
    result = resolve_assumptions("ACME", conn)
    assert result.tax_rate.value == pytest.approx(0.25)
    assert result.tax_rate.source is AssumptionSource.RULE_BASED


# --------------------------------------------------------------------------- #
# Dataset-region resolution (spec §5.1)                                        #
# --------------------------------------------------------------------------- #


def test_sector_joins_on_the_dataset_region_not_the_geographic_grouping(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The published country sheet stores "North America", the industry rows "US".

    Joining the two verbatim never matched, so every company resolved no sector row
    and to_dcf_assumptions() raised.
    """
    _seed_company(conn)
    _seed_industry(conn, region="US")
    _seed_country(conn, region="North America")
    result = resolve_assumptions("ACME", conn)
    assert result.operating_margin.value == pytest.approx((0.18,) * 5)
    assert result.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_cross_region_substitution_is_disclosed(conn: duckdb.DuckDBPyConnection) -> None:
    """A German company maps to "Europe", which has no ingested rows today.

    The US row is substituted rather than resolving nothing, and every value drawn
    from it is labelled so the report shows the substitution.
    """
    _seed_company(conn, ticker="DEU", country="Germany")
    _seed_industry(conn, region="US")
    _seed_country(conn, country="Germany", region="Western Europe")
    result = resolve_assumptions("DEU", conn)
    assert result.operating_margin.value == pytest.approx((0.18,) * 5)
    cross = AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION
    assert result.operating_margin.source is cross
    assert result.equity_weight.source is cross
    assert result.tax_rate.source is cross


def test_no_sector_row_at_all_is_not_reported_as_cross_region(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn, industry_damodaran="Nonexistent Industry")
    _seed_industry(conn, region="US")
    _seed_country(conn, region="North America")
    result = resolve_assumptions("ACME", conn)
    assert result.operating_margin.value is None
    # Unresolved, not a fabricated sector default and not mislabelled cross-region.
    assert result.operating_margin.source is AssumptionSource.UNRESOLVED


def test_assumptions_has_no_redundant_wacc_field() -> None:
    from dataclasses import fields

    from bot.valuator.assumptions import Assumptions

    # Deleted: to_dcf_assumptions() ignored it and the DCF recomputes WACC from
    # its components, so the field only ever produced a contradictory report.
    assert "wacc" not in {f.name for f in fields(Assumptions)}


def test_unresolved_assumption_reports_unresolved_not_a_sector_default(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # A company whose industry has no Damodaran row: the assumption has no value,
    # so claiming it came from the sector defaults is a lie the report would print.
    _seed_company(conn, ticker="OBSCURE", industry_damodaran="Obscure")
    result = resolve_assumptions("OBSCURE", conn)
    assert result.operating_margin.value is None
    assert result.operating_margin.source is AssumptionSource.UNRESOLVED


def test_resolved_assumption_still_reports_the_sector(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="SEMI", industry_damodaran="Software")
    _seed_industry(conn, op_margin=0.22)
    result = resolve_assumptions("SEMI", conn)
    assert result.operating_margin.value == pytest.approx((0.22,) * 5)
    assert result.operating_margin.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_partial_weight_override_is_honoured(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # Setting only equity_weight used to be discarded silently. The complement is
    # implied: weights partition capital.
    _seed_company(conn, ticker="LEV", industry_damodaran="Software")
    _seed_industry(conn, debt_to_equity=0.25)
    override = tmp_path / "LEV.yaml"
    override.write_text("equity_weight: 0.7\n")
    result = resolve_assumptions("LEV", conn, override_path=override)
    assert result.equity_weight.value == pytest.approx(0.7)
    assert result.debt_weight.value == pytest.approx(0.3)
    assert result.equity_weight.source is AssumptionSource.MANUAL
    assert result.debt_weight.source is AssumptionSource.MANUAL


def test_both_weights_overridden_must_partition(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # 0.7 + 0.4 used to resolve verbatim and flow into _wacc, producing a wrong
    # intrinsic value under a MANUAL provenance label.
    _seed_company(conn, ticker="BAD", industry_damodaran="Software")
    _seed_industry(conn, debt_to_equity=0.25)
    override = tmp_path / "BAD.yaml"
    override.write_text("equity_weight: 0.7\ndebt_weight: 0.4\n")
    with pytest.raises(ValueError, match=r"must sum to 1\.0"):
        resolve_assumptions("BAD", conn, override_path=override)


def test_both_weights_overridden_are_accepted_when_they_partition(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_company(conn, ticker="OK", industry_damodaran="Software")
    _seed_industry(conn, debt_to_equity=0.25)
    override = tmp_path / "OK.yaml"
    override.write_text("equity_weight: 0.65\ndebt_weight: 0.35\n")
    result = resolve_assumptions("OK", conn, override_path=override)
    assert result.equity_weight.value == pytest.approx(0.65)
    assert result.debt_weight.value == pytest.approx(0.35)
    assert result.equity_weight.source is AssumptionSource.MANUAL


def test_weights_always_partition(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="W", industry_damodaran="Software")
    _seed_industry(conn, debt_to_equity=0.25)
    result = resolve_assumptions("W", conn)
    assert result.equity_weight.value is not None and result.debt_weight.value is not None
    assert result.equity_weight.value + result.debt_weight.value == pytest.approx(1.0)


def test_unknown_override_key_is_rejected(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # A typo used to be ignored, so the user believed an override applied that did not.
    _seed_company(conn, ticker="TYPO", industry_damodaran="Software")
    override = tmp_path / "TYPO.yaml"
    override.write_text("terminal_grow: 0.02\n")
    with pytest.raises(ValueError, match="unknown override key"):
        resolve_assumptions("TYPO", conn, override_path=override)


def test_unknown_override_key_error_lists_the_valid_ones(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_company(conn, ticker="TYPO2", industry_damodaran="Software")
    override = tmp_path / "TYPO2.yaml"
    override.write_text("wacc: 0.09\n")
    with pytest.raises(ValueError, match="terminal_growth"):
        resolve_assumptions("TYPO2", conn, override_path=override)


def test_every_documented_override_key_is_accepted(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_company(conn, ticker="ALL", industry_damodaran="Software")
    override = tmp_path / "ALL.yaml"
    override.write_text(
        "revenue_growth: [0.1, 0.09, 0.08, 0.07, 0.06]\n"
        "operating_margin: 0.2\n"
        "sales_to_capital: 2.0\n"
        "terminal_growth: 0.02\n"
        "cost_of_equity: 0.09\n"
        "pretax_cost_of_debt: 0.05\n"
        "equity_weight: 0.8\n"
        "debt_weight: 0.2\n"
        "tax_rate: 0.25\n"
        "probability_of_bankruptcy: 0.05\n"
        "distress_value_per_share: 3.5\n"
        "story_type: high-growth\n"
        "notes: manual review\n"
    )
    result = resolve_assumptions("ALL", conn, override_path=override)
    assert result.story_type == "high-growth"
    assert result.notes == "manual review"
    assert result.distress_value_per_share.value == pytest.approx(3.5)
    assert result.distress_value_per_share.source is AssumptionSource.MANUAL


def test_distress_value_per_share_override_reaches_the_dcf(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """probability_of_bankruptcy and distress_value_per_share are a pair: the DCF
    blends a going-concern value with a liquidation value using both. A
    probability override with no reachable distress_value_per_share could only
    ever blend toward zero, so both must flow through to_dcf_assumptions()."""
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 110.0, 20.0), (2024, 121.0, 22.0)),
    )
    baseline = resolve_assumptions("ACME", conn, gdp_nominal=GDP_NOMINAL_US)
    assert baseline.distress_value_per_share.value == pytest.approx(0.0)
    assert baseline.distress_value_per_share.source is AssumptionSource.RULE_BASED
    baseline_dcf = baseline.to_dcf_assumptions()
    assert baseline_dcf.probability_of_bankruptcy == pytest.approx(0.0)
    assert baseline_dcf.distress_value_per_share == pytest.approx(0.0)

    override = tmp_path / "ACME.yaml"
    override.write_text(
        "probability_of_bankruptcy: 0.5\ndistress_value_per_share: 3.5\n"
    )
    distressed = resolve_assumptions(
        "ACME", conn, override_path=override, gdp_nominal=GDP_NOMINAL_US
    )
    assert distressed.probability_of_bankruptcy.value == pytest.approx(0.5)
    assert distressed.distress_value_per_share.value == pytest.approx(3.5)
    distressed_dcf = distressed.to_dcf_assumptions()
    assert distressed_dcf.probability_of_bankruptcy == pytest.approx(0.5)
    assert distressed_dcf.distress_value_per_share == pytest.approx(3.5)

    from bot.valuator.dcf import Financials, dcf

    financials = Financials(revenue=121.0, net_debt=50.0, shares_diluted=10.0)
    baseline_value = dcf(financials, baseline_dcf).intrinsic_value
    distressed_value = dcf(financials, distressed_dcf).intrinsic_value
    # Wiring is real, not cosmetic: blending in a 50% bankruptcy probability at a
    # distress value far below the going-concern value moves the intrinsic value.
    assert distressed_value != pytest.approx(baseline_value)


def test_assumption_source_has_no_unreachable_member() -> None:
    from bot.valuator.assumptions import AssumptionSource

    # ANALYST_CONSENSUS was never emitted by any resolver: revenue growth comes
    # from the historical average. Deleted so the enum describes what can happen.
    assert {s.value for s in AssumptionSource} == {
        "manual",
        "sector_default_damodaran",
        "sector_default_damodaran_cross_region",
        "rule_based",
        "historical_average",
        "story_pattern",
        "unresolved",
    }
