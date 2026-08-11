"""Damodaran columns derived from what the published files actually carry.

The published wacc.xls has no debt-to-equity column — it has D/(D+E). Without
deriving it, valuator/assumptions.py resolves equity_weight/debt_weight to None and
to_dcf_assumptions() raises, making the whole DCF unreachable in production.
"""

from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pytest

from bot.ingest.damodaran import (
    derive_industry_columns,
    parse_country_tax_rates,
    parse_preheader_scalar,
)
from bot.storage.db import apply_schema

_WACC_FIXTURE = Path("tests/fixtures/damodaran/wacc_sample.xls")
_CTRY_FIXTURE = Path("tests/fixtures/damodaran/ctryprem_sample.xls")

#: The additional published industry files (margins, sales-to-capital, multiples),
#: keyed by their INDUSTRY_DATASETS key.
_EXTRA_FIXTURES = {
    key: Path(f"tests/fixtures/damodaran/{key}_sample.xls")
    for key in ("margin", "capex", "pedata", "pbvdata", "vebitda", "psdata")
}

_ALL_FIXTURES_PRESENT = (
    _WACC_FIXTURE.exists()
    and _CTRY_FIXTURE.exists()
    and all(p.exists() for p in _EXTRA_FIXTURES.values())
)


def test_debt_to_equity_derived_from_debt_weight() -> None:
    # D/(D+E) = 0.2 -> D/E = 0.2 / 0.8 = 0.25
    row = derive_industry_columns({"debt_weight_raw": 0.2, "beta_levered": 1.0, "tax_rate": 0.25})
    assert row["debt_to_equity"] == pytest.approx(0.25)


def test_debt_to_equity_zero_debt() -> None:
    row = derive_industry_columns({"debt_weight_raw": 0.0})
    assert row["debt_to_equity"] == pytest.approx(0.0)


def test_debt_to_equity_all_debt_is_undefined_not_infinite() -> None:
    # D/(D+E) = 1 means zero equity: D/E is undefined, not inf. Must not poison
    # the DB with a non-finite double.
    row = derive_industry_columns({"debt_weight_raw": 1.0})
    assert row["debt_to_equity"] is None


def test_debt_to_equity_absent_input_leaves_column_absent() -> None:
    row = derive_industry_columns({"beta_levered": 1.1})
    assert row.get("debt_to_equity") is None


def test_beta_unlevered_derived() -> None:
    # bl / (1 + (1-t) * D/E) = 1.2 / (1 + 0.75 * 0.25) = 1.2 / 1.1875
    row = derive_industry_columns({"debt_weight_raw": 0.2, "beta_levered": 1.2, "tax_rate": 0.25})
    assert row["beta_unlevered"] == pytest.approx(1.2 / 1.1875)


def test_beta_unlevered_needs_beta_and_leverage() -> None:
    assert derive_industry_columns({"beta_levered": 1.2}).get("beta_unlevered") is None
    assert derive_industry_columns({"debt_weight_raw": 0.2}).get("beta_unlevered") is None


def test_derive_does_not_mutate_its_input() -> None:
    original = {"debt_weight_raw": 0.2, "beta_levered": 1.0, "tax_rate": 0.25}
    snapshot = dict(original)
    derive_industry_columns(original)
    assert original == snapshot


def test_derive_drops_the_helper_column() -> None:
    # debt_weight_raw is a parsing artefact, not a DB column.
    row = derive_industry_columns({"debt_weight_raw": 0.2})
    assert "debt_weight_raw" not in row


@pytest.mark.skipif(not _CTRY_FIXTURE.exists(), reason="country fixture absent")
def test_parse_country_tax_rates_from_the_real_workbook() -> None:
    rates = parse_country_tax_rates(_CTRY_FIXTURE)
    assert rates["Australia"] == pytest.approx(0.30)
    assert rates["Bahamas"] == pytest.approx(0.0)
    assert rates["Argentina"] == pytest.approx(0.35)
    assert all(0.0 <= v <= 1.0 for v in rates.values())
    assert "Country" not in rates


@pytest.mark.skipif(not _WACC_FIXTURE.exists(), reason="industry fixture absent")
def test_parse_preheader_scalar_finds_the_risk_free_rate() -> None:
    rfr = parse_preheader_scalar(
        _WACC_FIXTURE, "Industry Averages", "Long Term Treasury bond rate ="
    )
    assert rfr == pytest.approx(0.0395)


@pytest.mark.skipif(not _WACC_FIXTURE.exists(), reason="industry fixture absent")
def test_parse_preheader_scalar_unknown_label_returns_none() -> None:
    assert parse_preheader_scalar(_WACC_FIXTURE, "Industry Averages", "Nope =") is None


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="fixtures absent")
def test_dcf_assumptions_resolve_after_the_real_import() -> None:
    """The regression this task exists for: analyze() must not raise.

    Imports both real fixtures, then resolves the assumption bundle for a company
    in a mapped industry and projects it onto the pure DCF inputs. Before this
    task that projection raised ValueError on operating_margin / sales_to_capital
    / equity_weight, so `bot analyze` failed for every real company.
    """
    from bot.ingest.damodaran import import_damodaran_from_files
    from bot.valuator.assumptions import AssumptionSource, resolve_assumptions

    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths=dict(_EXTRA_FIXTURES),
    )
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES ('SEMI', 'Semi Co', 'United States', 'Semiconductors', 'Semiconductor', 'fmp')"
    )
    for year, revenue in ((2022, 100.0), (2023, 115.0), (2024, 130.0)):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, shares_diluted, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ["SEMI", year, revenue, revenue * 0.25, 10.0, "fmp"],
        )

    assumptions = resolve_assumptions("SEMI", conn)
    assert assumptions.equity_weight.value is not None
    assert assumptions.debt_weight.value is not None
    weights = assumptions.equity_weight.value + assumptions.debt_weight.value
    assert weights == pytest.approx(1.0), "equity + debt weights must be a partition"
    assert math.isfinite(assumptions.debt_weight.value)
    # The join now matches, so a US company resolves from the US dataset itself
    # rather than through a cross-region substitution.
    assert assumptions.equity_weight.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN

    # The projection that used to raise: all six critical assumptions resolve.
    dcf_inputs = assumptions.to_dcf_assumptions()
    assert dcf_inputs.operating_margin, "operating margin path must be non-empty"
    assert dcf_inputs.sales_to_capital > 0.0
    assert 0.0 < dcf_inputs.terminal_growth < 1.0


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="fixtures absent")
def test_analyze_values_a_us_company_after_the_real_import() -> None:
    """The phase's acceptance criterion: `bot analyze` no longer raises.

    Imports the full registry from the committed fixtures, seeds a US company with
    enough annual history, and runs the whole §7.7 pipeline. Before Tasks 1.4/1.5
    this raised ValueError on operating_margin / sales_to_capital / equity_weight
    for every real company, because wacc.xls alone never supplied those columns.
    """
    from bot.ingest.damodaran import import_damodaran_from_files
    from bot.valuator.analysis import analyze
    from bot.valuator.assumptions import AssumptionSource

    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths=dict(_EXTRA_FIXTURES),
    )
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry, industry_damodaran, source) "
        "VALUES ('SEMI', 'Semi Co', 'United States', 'USD', 'Semiconductors', "
        "'Semiconductor', 'fmp')"
    )
    for year, revenue in ((2022, 1000.0), (2023, 1150.0), (2024, 1300.0), (2025, 1450.0)):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, total_debt, cash, "
            "shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["SEMI", year, revenue, revenue * 0.22, revenue * 0.15, 200.0, 150.0,
             100.0, False, "fmp"],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) "
        "VALUES ('SEMI', '2026-08-07', 20.0, 'USD', 'fmp')"
    )

    result = analyze("SEMI", conn)

    assert result.dcf_result.intrinsic_value > 0.0
    assert result.dcf_result.enterprise_value > 0.0
    assert result.assumptions.equity_weight.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    # The six previously-unresolvable assumptions now resolve: to_dcf_assumptions()
    # no longer raises, and operating_margin / sales_to_capital carry real values
    # from the merged datasets rather than falling back to a global default.
    dcf_inputs = result.assumptions.to_dcf_assumptions()
    assert dcf_inputs.operating_margin, "operating margin path must be non-empty"
    assert dcf_inputs.sales_to_capital > 0.0
    # The §7.7 sanity check needs the multiples the extra datasets supply.
    assert result.sanity_check.sector_pe is not None
    assert result.sanity_check.sector_ev_sales is not None
    assert result.margin_of_safety is not None
    conn.close()
