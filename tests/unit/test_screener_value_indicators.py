"""Unit tests for the value-indicator rules (issue #5 / M3.4, spec §6.3).

Value indicators are *non-eliminatory individually* but at least one must pass
for a candidate to survive Capa B. Each cheap-vs-sector rule looks its benchmark
up from ``damodaran_industry`` (medians) via a shared helper that degrades
gracefully when the company's industry has no sector data: the rule is *skipped*
(flagged, not crashing) rather than silently failing.

Every rule gets: a below-threshold (pass) fixture, an above-threshold (fail)
fixture, and a no-sector-data (skip) fixture. The shared benchmark loader gets
its own DB-backed tests for present and missing industries.
"""

from __future__ import annotations

import duckdb
import pytest

from bot.screener.benchmarks import load_industry_benchmarks
from bot.screener.rules import (
    EVEBITDABelowIndustryMultiple,
    FCFYieldAbove,
    PBVBelowIndustryMultipleWithROEAboveMedian,
    PEBelowIndustryMultiple,
    get_rule,
)
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.storage.db import apply_schema, connect


def _company(**overrides: object) -> CompanyData:
    base: dict[str, object] = {
        "ticker": "AAA",
        "name": "Test Co",
        "industry": "Software",
        "region": "US",
    }
    base.update(overrides)
    return CompanyData(**base)  # type: ignore[arg-type]


def _benchmarks(**overrides: object) -> IndustryBenchmarks:
    base: dict[str, object] = {"industry": "Software", "region": "US", "year": 2025}
    base.update(overrides)
    return IndustryBenchmarks(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# PEBelowIndustryMultiple
# --------------------------------------------------------------------------- #
def test_pe_below_registered() -> None:
    assert get_rule("pe_below_industry_multiple") is PEBelowIndustryMultiple


def test_pe_below_passes_when_cheap() -> None:
    # industry median 20, default 0.7x -> threshold 14; PE 10 is below.
    result = PEBelowIndustryMultiple().evaluate(
        _company(pe=10.0), _benchmarks(pe=20.0)
    )
    assert result.passed is True
    assert result.skipped is False
    assert 0.0 <= result.score <= 1.0


def test_pe_below_fails_when_expensive() -> None:
    result = PEBelowIndustryMultiple().evaluate(
        _company(pe=18.0), _benchmarks(pe=20.0)
    )
    assert result.passed is False


def test_pe_below_skipped_when_no_sector_data() -> None:
    result = PEBelowIndustryMultiple().evaluate(
        _company(pe=10.0), _benchmarks(pe=None)
    )
    assert result.passed is False
    assert result.skipped is True
    assert "no sector" in result.reason.lower() or "median" in result.reason.lower()


def test_pe_below_skipped_when_company_pe_missing() -> None:
    result = PEBelowIndustryMultiple().evaluate(
        _company(pe=None), _benchmarks(pe=20.0)
    )
    assert result.passed is False
    assert result.skipped is True


def test_pe_below_skipped_when_company_pe_nonpositive() -> None:
    # A negative PE (losses) is meaningless as a cheapness signal -> skip.
    result = PEBelowIndustryMultiple().evaluate(
        _company(pe=-5.0), _benchmarks(pe=20.0)
    )
    assert result.skipped is True


def test_pe_below_configurable_multiple() -> None:
    # At 0.9x, threshold is 18; PE 16 now passes where it would fail at 0.7x.
    result = PEBelowIndustryMultiple(multiple=0.9).evaluate(
        _company(pe=16.0), _benchmarks(pe=20.0)
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# EVEBITDABelowIndustryMultiple
# --------------------------------------------------------------------------- #
def test_ev_ebitda_below_registered() -> None:
    assert get_rule("ev_ebitda_below_industry_multiple") is EVEBITDABelowIndustryMultiple


def test_ev_ebitda_below_passes_when_cheap() -> None:
    result = EVEBITDABelowIndustryMultiple().evaluate(
        _company(ev_ebitda=6.0), _benchmarks(ev_ebitda=12.0)
    )
    assert result.passed is True
    assert result.skipped is False


def test_ev_ebitda_below_fails_when_expensive() -> None:
    result = EVEBITDABelowIndustryMultiple().evaluate(
        _company(ev_ebitda=11.0), _benchmarks(ev_ebitda=12.0)
    )
    assert result.passed is False


def test_ev_ebitda_below_skipped_when_no_sector_data() -> None:
    result = EVEBITDABelowIndustryMultiple().evaluate(
        _company(ev_ebitda=6.0), _benchmarks(ev_ebitda=None)
    )
    assert result.skipped is True
    assert result.passed is False


def test_ev_ebitda_below_skipped_when_company_value_missing() -> None:
    result = EVEBITDABelowIndustryMultiple().evaluate(
        _company(ev_ebitda=None), _benchmarks(ev_ebitda=12.0)
    )
    assert result.skipped is True


def test_ev_ebitda_below_configurable_multiple() -> None:
    result = EVEBITDABelowIndustryMultiple(multiple=0.95).evaluate(
        _company(ev_ebitda=11.0), _benchmarks(ev_ebitda=12.0)
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# PBVBelowIndustryMultipleWithROEAboveMedian (combined check)
# --------------------------------------------------------------------------- #
def test_pbv_combined_registered() -> None:
    assert (
        get_rule("pbv_below_industry_multiple_with_roe_above_median")
        is PBVBelowIndustryMultipleWithROEAboveMedian
    )


def test_pbv_combined_passes_when_cheap_and_quality() -> None:
    # PBV 1.0 < 0.7*2.0=1.4 AND ROE 0.18 > median 0.12.
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=1.0, roe=0.18), _benchmarks(pbv=2.0, roe=0.12)
    )
    assert result.passed is True
    assert result.skipped is False


def test_pbv_combined_fails_when_cheap_but_low_roe() -> None:
    # Cheap on book value but ROE below median: classic value trap -> fail.
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=1.0, roe=0.08), _benchmarks(pbv=2.0, roe=0.12)
    )
    assert result.passed is False
    assert result.skipped is False


def test_pbv_combined_fails_when_high_roe_but_expensive() -> None:
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=1.8, roe=0.18), _benchmarks(pbv=2.0, roe=0.12)
    )
    assert result.passed is False


def test_pbv_combined_skipped_when_no_pbv_median() -> None:
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=1.0, roe=0.18), _benchmarks(pbv=None, roe=0.12)
    )
    assert result.skipped is True
    assert result.passed is False


def test_pbv_combined_skipped_when_no_roe_median() -> None:
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=1.0, roe=0.18), _benchmarks(pbv=2.0, roe=None)
    )
    assert result.skipped is True


def test_pbv_combined_skipped_when_company_data_missing() -> None:
    result = PBVBelowIndustryMultipleWithROEAboveMedian().evaluate(
        _company(pbv=None, roe=0.18), _benchmarks(pbv=2.0, roe=0.12)
    )
    assert result.skipped is True


def test_pbv_combined_configurable_multiple() -> None:
    result = PBVBelowIndustryMultipleWithROEAboveMedian(multiple=1.0).evaluate(
        _company(pbv=1.8, roe=0.18), _benchmarks(pbv=2.0, roe=0.12)
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# FCFYieldAbove (absolute threshold; no sector lookup)
# --------------------------------------------------------------------------- #
def test_fcf_yield_registered() -> None:
    assert get_rule("fcf_yield_above") is FCFYieldAbove


def test_fcf_yield_passes_above_threshold() -> None:
    result = FCFYieldAbove().evaluate(_company(fcf_yield=0.10), _benchmarks())
    assert result.passed is True
    assert result.skipped is False


def test_fcf_yield_fails_below_threshold() -> None:
    result = FCFYieldAbove().evaluate(_company(fcf_yield=0.05), _benchmarks())
    assert result.passed is False


def test_fcf_yield_skipped_when_missing() -> None:
    result = FCFYieldAbove().evaluate(_company(fcf_yield=None), _benchmarks())
    assert result.skipped is True
    assert result.passed is False


def test_fcf_yield_configurable_threshold() -> None:
    result = FCFYieldAbove(minimum=0.04).evaluate(
        _company(fcf_yield=0.05), _benchmarks()
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# Shared benchmark loader (handles missing industry data)
# --------------------------------------------------------------------------- #
@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, roic, roe, pe, pbv, ev_ebitda, "
        "op_margin, net_margin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["Software", "US", 2025, 0.09, 0.15, 0.20, 25.0, 4.0, 14.0, 0.25, 0.18],
    )
    return c


def test_load_benchmarks_returns_row(conn: duckdb.DuckDBPyConnection) -> None:
    bench = load_industry_benchmarks(conn, industry="Software", region="US", year=2025)
    assert bench is not None
    assert bench.industry == "Software"
    assert bench.region == "US"
    assert bench.year == 2025
    assert bench.pe == 25.0
    assert bench.pbv == 4.0
    assert bench.ev_ebitda == 14.0
    assert bench.roe == 0.20
    assert bench.wacc == 0.09
    assert bench.roic == 0.15


def test_load_benchmarks_missing_industry_returns_none(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    bench = load_industry_benchmarks(
        conn, industry="Nonexistent", region="US", year=2025
    )
    assert bench is None


def test_load_benchmarks_missing_industry_label_returns_none(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    bench = load_industry_benchmarks(conn, industry=None, region="US", year=2025)
    assert bench is None


def test_load_benchmarks_uses_latest_year_when_unspecified(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    conn.execute(
        "INSERT INTO damodaran_industry (industry, region, year, pe) "
        "VALUES (?, ?, ?, ?)",
        ["Software", "US", 2026, 19.0],
    )
    bench = load_industry_benchmarks(conn, industry="Software", region="US")
    assert bench is not None
    assert bench.year == 2026
    assert bench.pe == 19.0
