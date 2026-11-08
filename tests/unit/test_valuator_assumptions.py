"""Unit tests for assumptions resolution with source tracking (issue #12 / M4.2).

Spec §7.3: the six critical DCF assumptions, each carrying its provenance
(``source ∈ {manual, sector_default_damodaran,
sector_default_damodaran_cross_region, rule_based, historical_average,
unresolved}``). ``analyst_consensus`` was removed: nothing ever emitted it.
The resolution order is:

1. Manual override from ``config/assumptions/<TICKER>.yaml`` if present
2. Analyst consensus (FMP, M2 — for the M1 universe, fall back to historical)
3. Sector default from ``damodaran_industry`` / ``damodaran_country``
4. Rule-based (e.g. ``terminal_growth = min(rfr_ccy, gdp_ccy)``)

These tests exercise each branch in isolation against an in-memory DuckDB and a
temporary override file, so resolution stays a pure function of (ticker, conn,
override_path).
"""

from __future__ import annotations

import errno
import itertools
import re
from datetime import date
from pathlib import Path

import duckdb
import pytest
import yaml

from bot.reference.currencies import CurrencyRates, CurrencyTable
from bot.reference.default_spreads import (
    EMPTY_DEFAULT_SPREADS,
    CoverageBracket,
    DefaultProbability,
    DefaultSpreadTable,
)
from bot.storage.db import apply_schema, connect
from bot.valuator import assumptions as assumptions_mod
from bot.valuator.assumptions import (
    Assumptions,
    AssumptionSource,
    BankruptcyDerivation,
    Sourced,
    _linear_path,
    _resolve_revenue_growth,
    conventional_override_path,
    load_override,
    resolve_assumptions,
)
from bot.valuator.hypergrowth import StoryInputs, story_from_override
from bot.valuator.story_types import StoryType
from tests.unit.test_valuator_hypergrowth import _STORY

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

GDP_NOMINAL_US = 0.04  # rule-based terminal-growth cap input (US nominal GDP).


def _usd(rfr: float = 0.03, gdp: float = GDP_NOMINAL_US) -> CurrencyTable:
    """A one-row currency table for the USD companies these tests seed (#109)."""
    return {
        "USD": CurrencyRates(
            risk_free_rate=rfr,
            nominal_gdp_growth=gdp,
            source="https://example.org/rfr",
            gdp_source="https://example.org/gdp",
            as_of=date(2026, 1, 1),
        )
    }


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
    erp: float | None = 0.05,
    tax_rate: float | None = 0.21,
) -> None:
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, erp, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?)",
        [country, year, erp, tax_rate, region],
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
            "(ticker, fiscal_year, revenue, ebit, source, currency) VALUES (?, ?, ?, ?, ?, 'USD')",
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
    assert result.operating_margin.value == pytest.approx((0.18,) * 10)
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
    _seed_financials(conn, rows=((2024, 100.0, 18.0),))
    result = resolve_assumptions("ACME", conn, currencies=_usd())
    assert result.terminal_growth.value == pytest.approx(0.03)
    assert result.terminal_growth.source is AssumptionSource.RULE_BASED


def test_terminal_growth_capped_by_gdp_when_rfr_higher(conn: duckdb.DuckDBPyConnection) -> None:
    """rfr (0.06) > gdp (0.04) → terminal_growth = gdp."""
    _seed_company(conn)
    _seed_industry(conn)
    _seed_financials(conn, rows=((2024, 100.0, 18.0),))
    result = resolve_assumptions("ACME", conn, currencies=_usd(rfr=0.06))
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
    assert result.revenue_growth.value == pytest.approx(
        tuple(0.10 + (0.0395 - 0.10) * i / 9 for i in range(10))
    )


_SAWTOOTH = ((2021, 100.0, 18.0), (2022, 150.0, 27.0), (2023, 100.0, 18.0), (2024, 150.0, 27.0))


def test_revenue_growth_path_is_the_cagr_not_the_mean_of_yearly_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """100 → 150 → 100 → 150: CAGR ≈ 14.47%, not the 22.2% mean of yearly growth (#215)."""
    _seed_full_sector(conn)
    _seed_financials(conn, rows=_SAWTOOTH)
    result = resolve_assumptions("ACME", conn)
    assert result.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE
    path = result.revenue_growth.value
    assert path is not None
    # The fade starts at the CAGR (#215) and ends at terminal growth (#216).
    assert path[0] == pytest.approx(1.5 ** (1 / 3) - 1)
    assert path[-1] == result.terminal_growth.value


def test_both_loaders_give_the_cagr_growth_path(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=_SAWTOOTH)
    expected = (pytest.approx(1.5 ** (1 / 3) - 1),) * 10
    single = assumptions_mod.load_assumption_inputs(conn, "ACME", currencies=_usd())
    bulk = assumptions_mod.bulk_load_assumption_inputs(conn, ["ACME"], currencies=_usd())
    assert single.historical_growth_path == expected
    assert bulk["ACME"].historical_growth_path == expected


def test_revenue_growth_with_a_non_positive_last_revenue_has_no_history(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """A last revenue ≤ 0 makes the CAGR undefined: no history, GDP rule instead."""
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 100.0, 18.0), (2024, -10.0, -5.0)))
    result = resolve_assumptions("ACME", conn, currencies=_usd())
    assert result.revenue_growth.source is AssumptionSource.RULE_BASED


def test_revenue_growth_without_history_falls_back_to_rule_based_gdp(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """No financial history → rule-based path from nominal GDP fading to terminal growth."""
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2024, 100.0, 18.0),))
    result = resolve_assumptions("ACME", conn, currencies=_usd())
    path = result.revenue_growth.value
    assert result.revenue_growth.source is AssumptionSource.RULE_BASED
    assert len(path) == 10
    assert path[0] == pytest.approx(GDP_NOMINAL_US)
    assert path[-1] == result.terminal_growth.value


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

    assert result.operating_margin.value == pytest.approx((0.30,) * 10)
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

    assert result.operating_margin.value == pytest.approx((0.40,) * 10)
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


def test_override_that_is_not_yaml_is_refused(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """Malformed YAML is a ``ValueError``, so ``bot analyze`` moves on (#180)."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "revenue_growth: [0.1\n")
    with pytest.raises(ValueError, match=r"ACME\.yaml.*not valid YAML"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_with_a_non_string_key_is_refused(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "1: 2\nfoo: 3\n")
    with pytest.raises(ValueError, match=r"unknown override key\(s\): 1, foo"):
        resolve_assumptions("ACME", conn, override_path=override)


@pytest.mark.parametrize(
    ("body", "key"),
    [
        pytest.param("terminal_growth:\n", "terminal_growth", id="empty-value"),
        pytest.param("tax_rate: [0.2]\n", "tax_rate", id="list-for-a-number"),
        pytest.param("tax_rate: true\n", "tax_rate", id="bool"),
        pytest.param("sales_to_capital: {a: 1}\n", "sales_to_capital", id="mapping"),
        pytest.param("cost_of_equity: high\n", "cost_of_equity", id="word"),
        pytest.param("terminal_growth: .nan\n", "terminal_growth", id="nan"),
        pytest.param("terminal_growth: .inf\n", "terminal_growth", id="inf"),
        pytest.param("terminal_growth: 'nan'\n", "terminal_growth", id="string-nan"),
        pytest.param("terminal_growth: 1" + "0" * 400 + "\n", "terminal_growth", id="overflow"),
        pytest.param("operating_margin: []\n", "operating_margin", id="empty-path"),
        pytest.param("revenue_growth: [0.1, null]\n", "revenue_growth", id="null-in-path"),
        pytest.param("revenue_growth: [0.1, [0.2]]\n", "revenue_growth", id="list-in-path"),
    ],
)
def test_override_value_that_is_not_a_number_is_refused(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, body: str, key: str
) -> None:
    """Every numeric key holds a finite number, or a list of them for a path (#180)."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    with pytest.raises(ValueError, match=rf"ACME\.yaml: {key} must be"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_names_the_first_bad_value_in_file_order(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """With two bad values the refusal is stable: the first one written."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "tax_rate: [0.2]\ncost_of_equity: high\n")
    with pytest.raises(ValueError, match=r"ACME\.yaml: tax_rate must be"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_numeric_string_still_applies(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    """PyYAML reads an unquoted ``3e-2`` as a string; ``float()`` still takes it."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "terminal_growth: 3e-2\n")
    result = resolve_assumptions("ACME", conn, override_path=override)
    assert result.terminal_growth.value == pytest.approx(0.03)
    assert result.terminal_growth.source is AssumptionSource.MANUAL


@pytest.mark.parametrize(
    ("body", "key"),
    [
        pytest.param("tax_rate: 25\n", "tax_rate", id="percent-as-whole-number"),
        pytest.param("tax_rate: '25'\n", "tax_rate", id="percent-as-string"),
        pytest.param("probability_of_bankruptcy: 1.5\n", "probability_of_bankruptcy", id="pob"),
        pytest.param("equity_weight: -0.1\n", "equity_weight", id="negative-weight"),
        pytest.param("debt_weight: 1.2\n", "debt_weight", id="weight-above-one"),
        pytest.param("cost_of_equity: 0\n", "cost_of_equity", id="zero-cost-of-equity"),
        pytest.param("pretax_cost_of_debt: 1\n", "pretax_cost_of_debt", id="cost-of-debt-one"),
        pytest.param("terminal_growth: -1\n", "terminal_growth", id="terminal-growth"),
        pytest.param("sales_to_capital: 0\n", "sales_to_capital", id="zero-sales-to-capital"),
        pytest.param("distress_value_per_share: -1\n", "distress_value_per_share", id="distress"),
        pytest.param("operating_margin: [0.2, 1.0]\n", "operating_margin", id="margin-path"),
        pytest.param("operating_margin: 1.0\n", "operating_margin", id="margin-scalar"),
        pytest.param("revenue_growth: -1\n", "revenue_growth", id="growth-scalar"),
    ],
)
def test_override_value_outside_its_range_is_refused(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, body: str, key: str
) -> None:
    """A finite number its formula cannot take fails the ticker, not the DCF (#292)."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    with pytest.raises(ValueError, match=rf"ACME\.yaml: {key} must be"):
        resolve_assumptions("ACME", conn, override_path=override)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("tax_rate: 25\n", r"ACME\.yaml: tax_rate must be between 0 and 1, got 25$"),
        ("tax_rate: '25'\n", r"got '25'$"),
        (
            "revenue_growth: [0.1, -1.5, 0.1]\n",
            r"revenue_growth must be greater than -1 \(every element\), got \[0\.1, -1\.5, 0\.1\]$",
        ),
    ],
)
def test_override_range_error_names_the_range_and_the_value(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, body: str, message: str
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    with pytest.raises(ValueError, match=message):
        resolve_assumptions("ACME", conn, override_path=override)


@pytest.mark.parametrize(
    ("body", "field", "expected"),
    [
        ("tax_rate: 0\n", "tax_rate", 0.0),
        ("tax_rate: 1\n", "tax_rate", 1.0),
        ("probability_of_bankruptcy: 0\n", "probability_of_bankruptcy", 0.0),
        ("distress_value_per_share: 0\n", "distress_value_per_share", 0.0),
        ("operating_margin: -0.5\n", "operating_margin", (-0.5,) * 10),
        ("revenue_growth: 2.0\n", "revenue_growth", (2.0,) * 10),
    ],
)
def test_override_boundary_value_is_accepted(
    conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    body: str,
    field: str,
    expected: float | tuple[float, ...],
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    result = resolve_assumptions("ACME", conn, override_path=override)
    resolved = getattr(result, field)
    assert resolved.value == pytest.approx(expected)
    assert resolved.source is AssumptionSource.MANUAL


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("tax_rate: [0.2]\ncost_of_equity: 5\n", "tax_rate"),
        ("cost_of_equity: 5\ntax_rate: abc\n", "cost_of_equity"),
    ],
)
def test_override_type_and_range_errors_keep_file_order(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, body: str, key: str
) -> None:
    """Type and range share one pass: the first bad key written is the one named."""
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    with pytest.raises(ValueError, match=rf"ACME\.yaml: {key} must be"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_range_phrases() -> None:
    phrases = {key: rng.phrase() for key, rng in assumptions_mod._OVERRIDE_RANGES.items()}
    assert phrases == {
        "tax_rate": "between 0 and 1",
        "probability_of_bankruptcy": "between 0 and 1",
        "equity_weight": "between 0 and 1",
        "debt_weight": "between 0 and 1",
        "cost_of_equity": "greater than 0 and less than 1",
        "pretax_cost_of_debt": "greater than 0 and less than 1",
        "terminal_growth": "greater than -1 and less than 1",
        "sales_to_capital": "greater than 0",
        "distress_value_per_share": "at least 0",
        "operating_margin": "less than 1",
        "revenue_growth": "greater than -1",
    }


def test_every_numeric_override_key_has_a_range() -> None:
    numeric = (
        assumptions_mod._OVERRIDE_KEYS
        - assumptions_mod._OVERRIDE_TEXT_KEYS
        - assumptions_mod._OVERRIDE_STORY_KEYS
    )
    assert set(assumptions_mod._OVERRIDE_RANGES) == numeric


#: Range each numeric line of the example file states in its trailing comment.
_EXAMPLE_RANGE_COMMENTS = {
    "revenue_growth": "cada valor > -1",
    "operating_margin": "cada valor < 1",
    "sales_to_capital": "> 0",
    "terminal_growth": "-1 < x < 1, y menor que el WACC",
    "cost_of_equity": "0 < x < 1",
    "pretax_cost_of_debt": "0 < x < 1",
    "equity_weight": "0..1",
    "debt_weight": "0..1",
    "tax_rate": "0..1",
    "probability_of_bankruptcy": "0..1",
    "distress_value_per_share": ">= 0",
}


def test_example_file_with_every_numeric_line_uncommented_loads(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    example = (root / "config" / "assumptions" / "_EXAMPLE.yaml.example").read_text()
    lines = []
    comments = {}
    for line in example.splitlines():
        if line.startswith("# "):
            key = line.removeprefix("# ").split(":", 1)[0]
            if key in _EXAMPLE_RANGE_COMMENTS:
                line = line.removeprefix("# ")
                comments[key] = line.split("#", 1)[1]
        lines.append(line)
    assert set(comments) == set(_EXAMPLE_RANGE_COMMENTS)
    for key, expected in _EXAMPLE_RANGE_COMMENTS.items():
        assert expected in comments[key], key
    path = tmp_path / "EX.yaml"
    path.write_text("\n".join(lines) + "\n")
    assert set(_EXAMPLE_RANGE_COMMENTS) <= set(load_override(path))


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


def test_high_growth_revenue_path_fades_from_history_to_terminal_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    # 100 -> 130 -> 169: two YoY growths of 30% each → historical average 30%.
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 130.0, 20.0), (2024, 169.0, 22.0)),
    )
    a = resolve_assumptions("ACME", conn, currencies=_usd(), auto_story_type=StoryType.HIGH_GROWTH)
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source == AssumptionSource.STORY_PATTERN
    assert path[0] == pytest.approx(0.30, abs=0.01)
    assert path[-1] == pytest.approx(a.terminal_growth.value, abs=1e-9)
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
    assert a.operating_margin.value == (pytest.approx(0.10),) * 10
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


def _seed_declining(conn: duckdb.DuckDBPyConnection) -> None:
    """Sector margin 12%; the company's own margin erodes to 3.6 / 90 = 4%."""
    _seed_company(conn)
    _seed_industry(conn, op_margin=0.12)
    _seed_country(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 5.0), (2023, 95.0, 4.5), (2024, 90.0, 3.6)),
    )


def test_mature_decline_keeps_its_own_margin_flat(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_declining(conn)
    a = resolve_assumptions(
        "ACME", conn, auto_story_type=StoryType.MATURE_DECLINE, currencies=_usd()
    )
    assert a.operating_margin.value == (pytest.approx(0.04),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE
    assert a.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE


def test_mature_decline_without_own_margin_falls_back_to_sector(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    _seed_industry(conn, op_margin=0.12)
    _seed_country(conn)
    a = resolve_assumptions(
        "ACME", conn, auto_story_type=StoryType.MATURE_DECLINE, currencies=_usd()
    )
    assert a.operating_margin.value == (0.12,) * 10
    assert a.operating_margin.source == AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_manual_margin_beats_mature_decline(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_declining(conn)
    override = _write_override(
        tmp_path, "operating_margin: 0.25\nstory_type: mature-decline\n"
    )
    a = resolve_assumptions(
        "ACME",
        conn,
        override_path=override,
        auto_story_type=StoryType.MATURE_DECLINE,
        currencies=_usd(),
    )
    assert a.operating_margin.value == (0.25,) * 10
    assert a.operating_margin.source == AssumptionSource.MANUAL


def test_mature_decline_keeps_a_negative_own_margin(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn)
    _seed_industry(conn, op_margin=0.12)
    _seed_country(conn)
    _seed_financials(conn, rows=((2023, 100.0, 2.0), (2024, 90.0, -4.5)))
    a = resolve_assumptions(
        "ACME", conn, auto_story_type=StoryType.MATURE_DECLINE, currencies=_usd()
    )
    assert a.operating_margin.value == (pytest.approx(-0.05),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE


def test_manual_story_type_mature_decline_uses_own_margin(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_declining(conn)
    override = _write_override(tmp_path, "story_type: mature-decline\n")
    a = resolve_assumptions("ACME", conn, override_path=override, currencies=_usd())
    assert a.operating_margin.value == (pytest.approx(0.04),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE


def test_mature_decline_own_margin_needs_no_sector_row(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_company(conn, industry_damodaran="Obscure")
    _seed_country(conn)
    _seed_financials(conn, rows=((2023, 100.0, 5.0), (2024, 90.0, 3.6)))
    a = resolve_assumptions(
        "ACME", conn, auto_story_type=StoryType.MATURE_DECLINE, currencies=_usd()
    )
    assert a.operating_margin.value == (pytest.approx(0.04),) * 10
    assert a.operating_margin.source == AssumptionSource.HISTORICAL_AVERAGE


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
    assert a.operating_margin.value == (0.25,) * 10
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
    _seed_financials(conn, rows=((2024, 100.0, 18.0),))
    result = resolve_assumptions("ACME", conn, currencies=_usd())
    assert result.operating_margin.value is None
    assert result.operating_margin.source is AssumptionSource.UNRESOLVED
    assert result.sales_to_capital.value is None
    assert result.sales_to_capital.source is AssumptionSource.UNRESOLVED
    # Currency-derived rule-based terminal growth still resolves.
    assert result.terminal_growth.value == pytest.approx(0.03)


def test_to_dcf_assumptions_roundtrip(conn: duckdb.DuckDBPyConnection) -> None:
    """The resolved bundle converts into the pure dcf.Assumptions input."""
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 110.0, 20.0), (2024, 121.0, 22.0)),
    )
    result = resolve_assumptions("ACME", conn, currencies=_usd())
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
    assert result.operating_margin.value == pytest.approx((0.18,) * 10)
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
    assert result.operating_margin.value == pytest.approx((0.18,) * 10)
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
    assert result.operating_margin.value == pytest.approx((0.22,) * 10)
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
    baseline = resolve_assumptions("ACME", conn, currencies=_usd())
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
        "ACME", conn, override_path=override, currencies=_usd()
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
    """Every member is referenced by name somewhere in bot.valuator outside the
    enum body, and the member list is pinned."""
    import importlib
    import inspect
    import pkgutil
    import re

    import bot.valuator
    from bot.valuator.assumptions import AssumptionSource

    referenced: set[str] = set()
    for info in pkgutil.iter_modules(bot.valuator.__path__):
        module = importlib.import_module(f"bot.valuator.{info.name}")
        source = inspect.getsource(module)
        referenced |= set(re.findall(r"AssumptionSource\.([A-Z0-9_]+)", source))

    unreachable = {member.name for member in AssumptionSource} - referenced
    assert not unreachable, f"AssumptionSource members nothing emits: {sorted(unreachable)}"

    # ANALYST_CONSENSUS was never emitted by any resolver: revenue growth comes
    # from the historical average. Deleted so the enum describes what can happen.
    assert {s.value for s in AssumptionSource} == {
        "manual",
        "sector_default_damodaran",
        "sector_default_damodaran_cross_region",
        "rule_based",
        "historical_average",
        "story_pattern",
        "story",
        "unresolved",
    }


def test_high_growth_fade_starts_at_the_historical_average_not_year_one() -> None:
    # A year-varying history path: year-1 growth 50%, but the average is 18%.
    # The spec says the fade runs "promedio histórico → PBI nominal"; pin that
    # the start is the mean, not whatever happens to sit in historical[0].
    historical = (0.50, 0.10, 0.10, 0.10, 0.10)
    resolved = _resolve_revenue_growth(
        historical, {}, 0.04, terminal_growth=0.04, story_type=StoryType.HIGH_GROWTH
    )
    path = resolved.value
    assert path is not None
    assert path[0] == pytest.approx(0.18)  # fmean(historical), NOT 0.50
    assert path[-1] == pytest.approx(0.04)


# --------------------------------------------------------------------------- #
# conventional_override_path helper (Task 1)                                  #
# --------------------------------------------------------------------------- #


def test_conventional_override_path_finds_the_ticker_yaml(tmp_path: Path) -> None:
    (tmp_path / "AAPL.yaml").write_text("story_type: mature\n")
    assert conventional_override_path(tmp_path, "aapl") == tmp_path / "AAPL.yaml"


def test_conventional_override_path_is_none_when_missing_or_no_dir(tmp_path: Path) -> None:
    assert conventional_override_path(tmp_path, "MSFT") is None
    assert conventional_override_path(None, "MSFT") is None


def test_conventional_override_path_passes_a_directory_on(tmp_path: Path) -> None:
    """A directory named ``TICKER.yaml`` is handed to ``load_override``, which refuses it (#227)."""
    (tmp_path / "AAPL.yaml").mkdir()
    assert conventional_override_path(tmp_path, "AAPL") == tmp_path / "AAPL.yaml"


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(PermissionError(errno.EACCES, "Permission denied"), id="permission"),
        pytest.param(OSError(errno.EIO, "Input/output error"), id="io-error"),
    ],
)
def test_load_override_unreadable_file_is_a_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    path = tmp_path / "AAPL.yaml"
    path.write_text("notes: unreadable\n")
    real = Path.read_text

    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "AAPL.yaml":
            raise error
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(ValueError, match=re.escape(f"override file {path} cannot be read")) as exc:
        load_override(path)
    assert exc.value.__cause__ is error


def test_load_override_directory_is_a_value_error(tmp_path: Path) -> None:
    path = tmp_path / "AAPL.yaml"
    path.mkdir()
    with pytest.raises(ValueError, match=re.escape(f"override file {path} cannot be read")) as exc:
        load_override(path)
    assert isinstance(exc.value.__cause__, IsADirectoryError)


def test_cyclical_margin_needs_a_full_cycle_of_history() -> None:
    assert assumptions_mod._MIN_CYCLE_YEARS == 4


# --------------------------------------------------------------------------- #
# Hypergrowth story file keys (#194)                                           #
# --------------------------------------------------------------------------- #

_VALID_STORY = (
    "story:\n"
    "  year1_growth: 4.00\n"
    "  target_revenue_y10: 1011491000000\n"
    "  year1_margin: 0.05\n"
    "  target_margin: 0.325\n"
    "  sales_to_capital: 3.0\n"
    "  wacc_start: 0.0974\n"
)

_FULL_STORY_FILE = """\
story_type: hypergrowth
founded_year: 2021
story:
  year1_growth: 4.00
  target_revenue_y10: 1011491000000
  year1_margin: 0.05
  target_margin: 0.325
  margin_converge_year: 5
  regulatory_drag: 0.05
  sales_to_capital: 3.0
  wacc_start: 0.0974
  wacc_terminal: 0.0913
  effective_tax_rate: 0.0
  terminal_roic: 0.15
  failure_probability: 0.10
  failure_proceeds_pct_of_value: 0.50
  fixed_commitments_pv: 472336000000
  extra_cash: 100000000000
  governance_discount: 0.20
scenarios:
  worst: {target_revenue_y10: 200000000000, target_margin: 0.10, sales_to_capital: 1.0, wacc_start: 0.0988, regulatory_drag: 0.10}
  best:  {target_revenue_y10: 1500000000000, target_margin: 0.40, sales_to_capital: 4.0, wacc_start: 0.0779, regulatory_drag: 0.0}
"""


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        pytest.param(
            "story_type: hypergrowth\n", "requires a story", id="hypergrowth-without-story"
        ),
        pytest.param(
            "story_type: high-growth\n" + _VALID_STORY, "story_type", id="story-with-high-growth"
        ),
        pytest.param(_VALID_STORY, "story_type", id="story-without-story-type"),
        pytest.param(
            "scenarios: {worst: {target_margin: 0.1}}\n",
            "scenarios",
            id="scenarios-without-story",
        ),
        pytest.param("founded_year: 1500\n", "founded_year", id="founded-year-1500"),
        pytest.param("founded_year: 2021.5\n", "founded_year", id="founded-year-float"),
        pytest.param("founded_year: true\n", "founded_year", id="founded-year-bool"),
        pytest.param("story_type: hypergrowth\nstory:\n", "mapping", id="null-story"),
        pytest.param(
            "story_type: hypergrowth\nscenarios: 3\n" + _VALID_STORY,
            "scenarios",
            id="scenarios-not-mapping",
        ),
        pytest.param(
            "story_type: hypergrowth\n" + _VALID_STORY.replace("3.0", "0"),
            "story.sales_to_capital",
            id="story-parsed-at-load",
        ),
    ],
)
def test_load_override_rejects_story_file_errors(
    tmp_path: Path, body: str, fragment: str
) -> None:
    path = _write_override(tmp_path, body)
    with pytest.raises(ValueError) as excinfo:
        load_override(path)
    message = str(excinfo.value)
    assert message.startswith(f"{path}: ")
    assert fragment in message


def test_load_override_accepts_founded_year_up_to_this_year(tmp_path: Path) -> None:
    this_year = date.today().year
    path = _write_override(tmp_path, f"founded_year: {this_year}\n")
    assert load_override(path) == {"founded_year": this_year}
    path.write_text(f"founded_year: {this_year + 1}\n")
    with pytest.raises(ValueError, match="founded_year"):
        load_override(path)


def test_load_override_full_story_file(tmp_path: Path) -> None:
    path = _write_override(tmp_path, _FULL_STORY_FILE)
    parsed = story_from_override(load_override(path), where=str(path))
    assert parsed is not None
    story, scenarios = parsed
    assert isinstance(story, StoryInputs)
    assert story.target_revenue_y10 == 1_011_491_000_000
    assert list(scenarios) == ["worst", "best"]


def test_load_override_without_a_path_is_empty(tmp_path: Path) -> None:
    assert load_override(None) == {}
    assert load_override(tmp_path / "MISSING.yaml") == {}


def test_founded_year_is_accepted_with_any_story_type(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "founded_year: 1976\nstory_type: mature-stable\n")
    result = resolve_assumptions("ACME", conn, override_path=override)
    assert result.story_type == "mature-stable"


# --------------------------------------------------------------------------- #
# Hypergrowth gate on the story file (#195)                                    #
# --------------------------------------------------------------------------- #


def _story_override(tmp_path: Path, **extra: object) -> Path:
    # sort_keys=False: scenario order is file order.
    body = {"story_type": "hypergrowth", "story": _STORY, **extra}
    return _write_override(tmp_path, yaml.safe_dump(body, sort_keys=False))


def test_hypergrowth_without_story_falls_back_to_high_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions("ACME", conn, auto_story_type=StoryType.HYPERGROWTH)
    assert result.story_type == "high-growth"


def test_hypergrowth_fallback_is_logged(conn: duckdb.DuckDBPyConnection) -> None:
    from structlog.testing import capture_logs

    _seed_full_sector(conn)
    with capture_logs() as events:
        resolve_assumptions("ACME", conn, auto_story_type=StoryType.HYPERGROWTH)
    event = "assumptions.story_type.hypergrowth_without_story"
    fallbacks = [e for e in events if e.get("event") == event]
    assert [e["ticker"] for e in fallbacks] == ["ACME"]


def test_hypergrowth_with_story_keeps_label_and_story_resolvers(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # #196: with a story the label is hypergrowth and the story drives the growth.
    # Raw dollars, the story's units (Damodaran's 2026-11-03 sheet).
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2024, 1_020e6, -2_325e6), (2025, 35_286e6, -46_313e6)))
    override = load_override(_story_override(tmp_path))
    result = resolve_assumptions(
        "ACME", conn, override=override, auto_story_type=StoryType.HYPERGROWTH
    )
    assert result.story_type == "hypergrowth"
    assert result.revenue_growth.source is AssumptionSource.STORY


def test_manual_story_type_beats_hypergrowth_gate(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "story_type: mature-stable\n")
    result = resolve_assumptions(
        "ACME", conn, override_path=override, auto_story_type=StoryType.HYPERGROWTH
    )
    assert result.story_type == "mature-stable"


def test_override_mapping_wins_over_path(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    path = _write_override(tmp_path, "operating_margin: 0.10\n")
    result = resolve_assumptions(
        "ACME", conn, override_path=path, override={"operating_margin": 0.35}
    )
    assert result.operating_margin.value == pytest.approx((0.35,) * 10)
    assert result.operating_margin.source is AssumptionSource.MANUAL


# --- #196: story fields of the bundle, latest revenue --------------------------


def test_generic_bundle_has_no_story_fields(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 100.0, 18.0), (2024, 110.0, 20.0)))
    result = resolve_assumptions("ACME", conn, currencies=_usd())
    for name in (
        "wacc_path",
        "tax_rate_path",
        "terminal_roic",
        "distress_proceeds_pct",
        "fixed_commitments",
        "extra_cash",
        "governance_discount",
        "story",
        "bankruptcy_derivation",
    ):
        assert getattr(result, name) is None, name
    dcf_assumptions = result.to_dcf_assumptions()
    assert dcf_assumptions.wacc_path is None
    assert dcf_assumptions.tax_rate_path is None
    assert dcf_assumptions.terminal_roic is None
    assert dcf_assumptions.distress_proceeds_pct is None


def test_latest_revenue_loaded_per_ticker_and_bulk(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 100.0, 18.0), (2024, 110.0, 20.0)))
    conn.execute(
        "INSERT INTO financials_annual "
        "(ticker, fiscal_year, revenue, ebit, is_restated, source, currency) "
        "VALUES ('ACME', 2025, 999.0, 1.0, TRUE, 'test', 'USD')"
    )
    single = assumptions_mod.load_assumption_inputs(conn, "ACME", currencies=_usd())
    bulk = assumptions_mod.bulk_load_assumption_inputs(conn, ["ACME"], currencies=_usd())
    assert single.latest_revenue == 110.0
    assert bulk["ACME"].latest_revenue == 110.0
    assert single == bulk["ACME"]


def test_latest_revenue_is_none_without_financials(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    assert assumptions_mod.load_assumption_inputs(conn, "ACME", currencies=_usd()).latest_revenue is None
    bulk = assumptions_mod.bulk_load_assumption_inputs(conn, ["ACME"], currencies=_usd())
    assert bulk["ACME"].latest_revenue is None


def test_resolve_hypergrowth_story_raises_without_latest_revenue(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, revenue, ebit, source, currency) "
        "VALUES ('ACME', 2024, NULL, 1.0, 'test', 'USD')"
    )
    with pytest.raises(ValueError, match=r"ACME.*revenue"):
        resolve_assumptions(
            "ACME", conn, override_path=_story_override(tmp_path), currencies=_usd()
        )


def test_resolve_hypergrowth_story_applies_the_story(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 1.0e9, -1.0e9), (2024, 20.0e9, -40.0e9)))
    result = resolve_assumptions(
        "ACME",
        conn,
        override_path=_story_override(tmp_path, terminal_growth=0.049),
        currencies=_usd(),
    )
    assert result.story_type == "hypergrowth"
    assert result.revenue_growth.source is AssumptionSource.STORY
    assert result.revenue_growth.value is not None
    assert len(result.revenue_growth.value) == 10
    assert result.terminal_growth.source is AssumptionSource.MANUAL
    assert result.story is not None


def test_resolve_hypergrowth_story_falls_back_to_the_sector_wacc(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)  # sector wacc 0.09
    _seed_financials(conn, rows=((2023, 1.0e9, -1.0e9), (2024, 20.0e9, -40.0e9)))
    story = {k: v for k, v in _STORY.items() if k != "wacc_terminal"}
    path = tmp_path / "ACME.yaml"
    path.write_text(yaml.safe_dump({"story_type": "hypergrowth", "story": story}))
    result = resolve_assumptions("ACME", conn, override_path=path, currencies=_usd())
    assert result.wacc_path is not None
    assert result.wacc_path.value[-1] == 0.09


# --- #197: scenarios on the bundle ----------------------------------------------


def test_resolve_sets_scenarios_from_the_story_file(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 1.0e9, -1.0e9), (2024, 20.0e9, -40.0e9)))
    scenarios = {
        "worst": {"target_revenue_y10": 200e9, "target_margin": 0.10},
        "best": {"target_revenue_y10": 1_500e9},
    }
    result = resolve_assumptions(
        "ACME",
        conn,
        override_path=_story_override(tmp_path, terminal_growth=0.049, scenarios=scenarios),
        currencies=_usd(),
    )
    assert result.scenarios is not None
    assert list(result.scenarios) == ["worst", "best"]
    assert all(isinstance(s, StoryInputs) for s in result.scenarios.values())
    assert result.scenarios["worst"].target_margin == 0.10
    assert result.scenarios["best"].target_margin == _STORY["target_margin"]


def test_resolve_without_scenarios_leaves_them_none(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2023, 1.0e9, -1.0e9), (2024, 20.0e9, -40.0e9)))
    storied = resolve_assumptions(
        "ACME",
        conn,
        override_path=_story_override(tmp_path, terminal_growth=0.049),
        currencies=_usd(),
    )
    plain = resolve_assumptions("ACME", conn, currencies=_usd())
    assert storied.scenarios is None
    assert plain.scenarios is None


# --------------------------------------------------------------------------- #
# #216: every non-manual growth path fades to terminal growth over 10 years    #
# --------------------------------------------------------------------------- #

#: Terminal growth of the default USD row: min(rfr 0.0395, GDP 0.04).
_G_TERMINAL_USD = 0.0395


def _seed_18pct_history(conn: duckdb.DuckDBPyConnection) -> None:
    # 100 -> 118 -> 139.24: two YoY growths of 18% (mean == CAGR here).
    _seed_financials(
        conn, rows=((2022, 100.0, 18.0), (2023, 118.0, 20.0), (2024, 139.24, 22.0))
    )


def test_mature_stable_growth_fades_from_history_to_terminal_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    _seed_18pct_history(conn)
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.MATURE_STABLE)
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE
    assert path == pytest.approx(
        tuple(0.18 + (_G_TERMINAL_USD - 0.18) * i / 9 for i in range(10))
    )
    assert len(path) == 10
    assert path[-1] == a.terminal_growth.value == _G_TERMINAL_USD


def test_high_growth_fades_to_terminal_growth_not_gdp(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 18.0), (2023, 130.0, 20.0), (2024, 169.0, 22.0)),
    )
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source is AssumptionSource.STORY_PATTERN
    assert len(path) == 10
    assert path[0] == pytest.approx(0.30)
    assert path[-1] == _G_TERMINAL_USD


def test_manual_terminal_growth_is_the_fade_target(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_18pct_history(conn)
    override = _write_override(tmp_path, "terminal_growth: 0.02\n")
    a = resolve_assumptions("ACME", conn, override_path=override)
    path = a.revenue_growth.value
    assert path is not None
    assert len(path) == 10
    assert path[0] == pytest.approx(0.18)
    assert path[-1] == 0.02


def test_manual_terminal_growth_fades_even_with_an_uncovered_currency(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_18pct_history(conn)
    override = _write_override(tmp_path, "terminal_growth: 0.02\n")
    a = resolve_assumptions("ACME", conn, override_path=override, currencies={})
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE
    assert len(path) == 10
    assert path[-1] == 0.02


def test_growth_without_history_fades_from_gdp_to_terminal_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    _seed_financials(conn, rows=((2024, 100.0, 18.0),))
    a = resolve_assumptions("ACME", conn, currencies=_usd(rfr=0.03))
    path = a.revenue_growth.value
    assert path is not None
    assert a.revenue_growth.source is AssumptionSource.RULE_BASED
    assert len(path) == 10
    assert path[0] == pytest.approx(GDP_NOMINAL_US)
    assert path[-1] == 0.03


def test_growth_is_unresolved_without_terminal_growth() -> None:
    resolved = _resolve_revenue_growth((0.1,) * 10, {}, None, terminal_growth=None)
    assert resolved.value is None
    assert resolved.source is AssumptionSource.UNRESOLVED


def test_manual_growth_list_keeps_its_length(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_18pct_history(conn)
    override = _write_override(tmp_path, "revenue_growth: [0.1, 0.1, 0.1, 0.1, 0.1]\n")
    a = resolve_assumptions("ACME", conn, override_path=override)
    assert a.revenue_growth.value == (0.1,) * 5
    assert a.revenue_growth.source is AssumptionSource.MANUAL
    assert len(a.to_dcf_assumptions().operating_margin) == 5


def test_manual_growth_scalar_repeats_over_ten_years(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    _seed_18pct_history(conn)
    override = _write_override(tmp_path, "revenue_growth: 0.07\n")
    a = resolve_assumptions("ACME", conn, override_path=override)
    assert a.revenue_growth.value == (0.07,) * 10
    assert a.revenue_growth.source is AssumptionSource.MANUAL


def test_high_growth_margin_ramp_has_ten_points(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn)
    _seed_industry(conn, op_margin=0.20)
    _seed_country(conn)
    _seed_financials(
        conn,
        rows=((2022, 100.0, 8.0), (2023, 110.0, 8.8), (2024, 121.0, 9.68)),
    )
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.HIGH_GROWTH)
    path = a.operating_margin.value
    assert path is not None
    assert len(path) == 10
    assert path[0] == pytest.approx(0.08)
    assert path[-1] == pytest.approx(0.20)


def test_linear_path_of_zero_or_one_steps() -> None:
    assert _linear_path(0.18, 0.0395, 0) == ()
    assert _linear_path(0.18, 0.0395, 1) == (0.0395,)


def test_linear_path_ends_exactly_on_its_target() -> None:
    path = _linear_path(0.18, 0.0395, 10)
    assert len(path) == 10
    assert path[-1] == 0.0395


# --------------------------------------------------------------------------- #
# Distressed: probability of bankruptcy from interest coverage (#246)          #
# --------------------------------------------------------------------------- #

_SPREADS_SOURCE = "https://example.org/spreads"


def _spreads() -> DefaultSpreadTable:
    """Inline table: horizon 10; coverage < 1.0 is CCC (0.59), the rest BBB (0.075)."""
    as_of = date(2026, 1, 1)
    return DefaultSpreadTable(
        horizon_years=10,
        brackets=(
            CoverageBracket(None, 1.0, "CCC", _SPREADS_SOURCE, as_of),
            CoverageBracket(1.0, None, "BBB", _SPREADS_SOURCE, as_of),
        ),
        probabilities={
            "CCC": DefaultProbability(0.59, _SPREADS_SOURCE, as_of),
            "BBB": DefaultProbability(0.075, _SPREADS_SOURCE, as_of),
        },
    )


_UNKNOWN_COVERAGE_REASON = (
    "distressed, but interest coverage is unknown (no EBIT or no interest expense): p stays 0"
)
_EMPTY_TABLE_REASON = (
    "distressed, but the default-spread table is empty "
    "(config/default_spreads.yaml absent or malformed): p stays 0"
)


def test_distressed_probability_comes_from_the_coverage_rating(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=0.6,
        default_spreads=_spreads(),
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == 0.59
    assert result.probability_of_bankruptcy.source is AssumptionSource.RULE_BASED
    assert result.bankruptcy_derivation == BankruptcyDerivation(
        0.6,
        "CCC",
        10,
        0.59,
        "interest coverage 0.60 → rating CCC → 10-year cumulative default probability 59.0%",
    )


def test_manual_probability_beats_the_table(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        _write_override(tmp_path, "probability_of_bankruptcy: 0.1\n"),
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=0.6,
        default_spreads=_spreads(),
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == pytest.approx(0.1)
    assert result.probability_of_bankruptcy.source is AssumptionSource.MANUAL
    assert result.bankruptcy_derivation is None


def test_distressed_without_coverage_keeps_zero_and_says_why(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=None,
        default_spreads=_spreads(),
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == 0.0
    assert result.probability_of_bankruptcy.source is AssumptionSource.RULE_BASED
    derivation = result.bankruptcy_derivation
    assert derivation is not None
    assert derivation.reason == _UNKNOWN_COVERAGE_REASON
    assert derivation.rating is None
    assert derivation.probability == 0.0


def test_distressed_with_an_empty_table_keeps_zero_and_says_why(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=0.6,
        default_spreads=EMPTY_DEFAULT_SPREADS,
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == 0.0
    assert result.probability_of_bankruptcy.source is AssumptionSource.RULE_BASED
    derivation = result.bankruptcy_derivation
    assert derivation is not None
    assert derivation.reason == _EMPTY_TABLE_REASON
    assert derivation.rating is None


def test_non_distressed_story_ignores_coverage(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.MATURE_STABLE,
        interest_coverage=0.6,
        default_spreads=_spreads(),
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == 0.0
    assert result.probability_of_bankruptcy.source is AssumptionSource.RULE_BASED
    assert result.bankruptcy_derivation is None


def test_negative_coverage_takes_the_lowest_bracket(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_full_sector(conn)
    result = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=-0.5,
        default_spreads=_spreads(),
        currencies=_usd(),
    )
    assert result.probability_of_bankruptcy.value == 0.59
    derivation = result.bankruptcy_derivation
    assert derivation is not None
    assert derivation.rating == "CCC"
    assert derivation.reason.startswith("interest coverage -0.50 → rating CCC")


def _count_default_loads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def _load() -> DefaultSpreadTable:
        calls.append(1)
        return _spreads()

    monkeypatch.setattr(assumptions_mod, "load_default_spreads", _load)
    return calls


def test_distressed_loads_the_default_table_when_none_is_given(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_full_sector(conn)
    calls = _count_default_loads(monkeypatch)

    distressed = resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=0.6,
        currencies=_usd(),
    )
    assert len(calls) == 1
    assert distressed.probability_of_bankruptcy.value == 0.59

    resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.MATURE_STABLE,
        interest_coverage=0.6,
        currencies=_usd(),
    )
    assert len(calls) == 1

    resolve_assumptions(
        "ACME",
        conn,
        _write_override(tmp_path, "probability_of_bankruptcy: 0.1\n"),
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=0.6,
        currencies=_usd(),
    )
    assert len(calls) == 1


def test_distressed_without_coverage_does_not_load_the_table(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_full_sector(conn)
    calls = _count_default_loads(monkeypatch)
    resolve_assumptions(
        "ACME",
        conn,
        auto_story_type=StoryType.DISTRESSED,
        interest_coverage=None,
        currencies=_usd(),
    )
    assert calls == []
