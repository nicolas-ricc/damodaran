"""Named coverage-gate reasons and the uncovered-currency exclusion (#109, ADR 0006).

A company the screener cannot measure leaves the universe before evaluation,
now with one named reason (``industry_unmapped`` > ``benchmark_missing`` >
``currency_uncovered``) instead of the bare ``coverage_gate`` marker, and the
screen result counts exclusions per reason.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
from bot.reference.currencies import CurrencyRates, CurrencyTable, load_currency_table
from structlog.testing import capture_logs

from bot.reporting.screen_report import render_markdown
from bot.screener.config import ScreenerConfig, load_screener_config
from bot.screener.engine import CoverageReason, RejectedCompany, ScreenResult, run_screen
from bot.storage.db import apply_schema, connect

PRESET = Path(__file__).resolve().parents[2] / "config" / "presets" / "damodaran_value.yaml"


def _rates(rfr: float, gdp: float) -> CurrencyRates:
    return CurrencyRates(
        risk_free_rate=rfr,
        nominal_gdp_growth=gdp,
        source="https://example.org/rfr",
        gdp_source="https://example.org/gdp",
        as_of=date(2026, 1, 1),
    )


TABLE: CurrencyTable = {"USD": _rates(0.0395, 0.04), "JPY": _rates(0.0147, 0.0261)}


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES ('United States', 2026, 'US')"
    )
    c.execute(
        "INSERT INTO damodaran_industry (industry, region, year, wacc, pe) "
        "VALUES ('Software', 'US', 2026, 0.08, 20.0), ('Retail (General)', 'US', 2026, NULL, 15.0)"
    )
    return c


def _preset() -> ScreenerConfig:
    return load_screener_config(PRESET)


def _company(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    industry_damodaran: str | None = "Software",
    currency: str | None = "USD",
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, 'United States', 'Provider Label', ?, 'fmp')",
        [ticker, f"{ticker} Corp", industry_damodaran],
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, currency, revenue, ebit, source) "
        "VALUES (?, 2025, ?, 1000.0, 200.0, 'fmp')",
        [ticker, currency],
    )


def _reasons(result: ScreenResult) -> dict[str, tuple[str, ...]]:
    return {r.ticker: r.failed_gates for r in result.rejected}


def test_each_coverage_exclusion_carries_its_named_reason(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _company(conn, "NOMAP", industry_damodaran=None)
    _company(conn, "NOBENCH", industry_damodaran="Software (System)")
    _company(conn, "NULLWACC", industry_damodaran="Retail (General)")
    _company(conn, "YEN", currency="XYZ")

    result = run_screen(conn, _preset(), valuator=None, currencies=TABLE)

    reasons = _reasons(result)
    assert reasons["NOMAP"] == ("industry_unmapped",)
    assert reasons["NOBENCH"] == ("benchmark_missing",)
    assert reasons["NULLWACC"] == ("benchmark_missing",)
    assert reasons["YEN"] == ("currency_uncovered",)
    assert result.no_coverage == ("NOBENCH", "NOMAP", "NULLWACC", "YEN")
    assert result.coverage_counts == {
        CoverageReason.INDUSTRY_UNMAPPED: 1,
        CoverageReason.BENCHMARK_MISSING: 2,
        CoverageReason.CURRENCY_UNCOVERED: 1,
    }
    assert result.screened == 0


def test_uncovered_currency_is_counted_separately_from_benchmark_missing(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _company(conn, "XCO", currency="XYZ")
    result = run_screen(conn, _preset(), valuator=None, currencies=TABLE)
    assert result.coverage_counts[CoverageReason.CURRENCY_UNCOVERED] == 1
    assert result.coverage_counts[CoverageReason.BENCHMARK_MISSING] == 0


def test_covered_jpy_company_is_screened(conn: duckdb.DuckDBPyConnection) -> None:
    _company(conn, "TOYO", currency="JPY")
    result = run_screen(conn, _preset(), valuator=None, currencies=TABLE)
    assert result.no_coverage == ()
    assert result.screened == 1


@pytest.mark.parametrize("currency", [None, "jpy"])
def test_currency_is_normalised_and_null_is_uncovered(
    conn: duckdb.DuckDBPyConnection, currency: str | None
) -> None:
    _company(conn, "CO", currency=currency)
    result = run_screen(conn, _preset(), valuator=None, currencies=TABLE)
    expected = () if currency == "jpy" else ("CO",)
    assert result.no_coverage == expected


def test_missing_currency_file_excludes_every_company_as_currency_uncovered(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _company(conn, "AAA")
    _company(conn, "BBB", currency="JPY")
    with capture_logs() as logs:
        result = run_screen(
            conn, _preset(), valuator=None, currencies=load_currency_table(tmp_path / "gone.yaml")
        )
    assert "currencies.absent" in [e["event"] for e in logs]
    assert _reasons(result) == {
        "AAA": ("currency_uncovered",),
        "BBB": ("currency_uncovered",),
    }


def test_currency_uncovered_warns_once_per_currency(conn: duckdb.DuckDBPyConnection) -> None:
    _company(conn, "XA", currency="XYZ")
    _company(conn, "XB", currency="XYZ")
    with capture_logs() as logs:
        run_screen(conn, _preset(), valuator=None, currencies=TABLE)
    events = [e for e in logs if e["event"] == "screener.currency_uncovered"]
    assert len(events) == 1
    assert events[0]["currency"] == "XYZ"


def test_coverage_counts_cover_every_reason_even_when_zero() -> None:
    result = ScreenResult(preset="p", shortlist=(), screened=0)
    assert result.coverage_counts == dict.fromkeys(CoverageReason, 0)


def test_markdown_reports_coverage_counts_by_reason() -> None:
    result = ScreenResult(
        preset="p",
        shortlist=(),
        screened=0,
        no_coverage=("A", "B", "C"),
        rejected=(
            RejectedCompany("A", ("industry_unmapped",)),
            RejectedCompany("B", ("currency_uncovered",)),
            RejectedCompany("C", ("currency_uncovered",)),
        ),
    )
    text = render_markdown(result, generated_on=date(2026, 10, 28))
    assert "industry_unmapped 1" in text
    assert "benchmark_missing 0" in text
    assert "currency_uncovered 2" in text
