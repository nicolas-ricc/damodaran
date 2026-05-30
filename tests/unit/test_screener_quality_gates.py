"""Unit tests for the eliminatory quality-gate rules (issue #4 / M3.3, spec §6.2).

Every gate gets a passing and a failing fixture, a missing-data check, and a
configurable-threshold check. Gates are eliminatory: a company that cannot be
measured (missing datum) fails the gate, since the screener will not vouch for a
company it cannot assess.
"""

from __future__ import annotations

import pytest

from bot.screener.rules import (
    ExcludeSectors,
    MaxGoodwillToAssets,
    MaxNetDebtToEBITDA,
    MinInterestCoverage,
    MinMarketCap,
    MinYearsHistory,
    PositiveOperatingCashflow,
    get_rule,
)
from bot.screener.types import CompanyData, IndustryBenchmarks


@pytest.fixture
def benchmarks() -> IndustryBenchmarks:
    return IndustryBenchmarks(industry="Software", region="US", year=2025)


def _company(**overrides: object) -> CompanyData:
    base: dict[str, object] = {"ticker": "AAA", "name": "Test Co"}
    base.update(overrides)
    return CompanyData(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# MinMarketCap
# --------------------------------------------------------------------------- #
def test_min_market_cap_registered() -> None:
    assert get_rule("min_market_cap") is MinMarketCap


def test_min_market_cap_pass(benchmarks: IndustryBenchmarks) -> None:
    result = MinMarketCap().evaluate(_company(market_cap=5e9), benchmarks)
    assert result.passed is True


def test_min_market_cap_fail(benchmarks: IndustryBenchmarks) -> None:
    result = MinMarketCap().evaluate(_company(market_cap=5e7), benchmarks)
    assert result.passed is False


def test_min_market_cap_missing_fails(benchmarks: IndustryBenchmarks) -> None:
    result = MinMarketCap().evaluate(_company(market_cap=None), benchmarks)
    assert result.passed is False
    assert "unavailable" in result.reason


def test_min_market_cap_configurable(benchmarks: IndustryBenchmarks) -> None:
    result = MinMarketCap(minimum_usd=1e7).evaluate(_company(market_cap=5e7), benchmarks)
    assert result.passed is True


# --------------------------------------------------------------------------- #
# MinYearsHistory
# --------------------------------------------------------------------------- #
def test_min_years_history_registered() -> None:
    assert get_rule("min_years_history") is MinYearsHistory


def test_min_years_history_pass(benchmarks: IndustryBenchmarks) -> None:
    result = MinYearsHistory().evaluate(_company(years_of_financials=6), benchmarks)
    assert result.passed is True


def test_min_years_history_fail(benchmarks: IndustryBenchmarks) -> None:
    result = MinYearsHistory().evaluate(_company(years_of_financials=3), benchmarks)
    assert result.passed is False


def test_min_years_history_boundary(benchmarks: IndustryBenchmarks) -> None:
    result = MinYearsHistory().evaluate(_company(years_of_financials=5), benchmarks)
    assert result.passed is True


def test_min_years_history_configurable(benchmarks: IndustryBenchmarks) -> None:
    result = MinYearsHistory(minimum_years=3).evaluate(
        _company(years_of_financials=3), benchmarks
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# ExcludeSectors
# --------------------------------------------------------------------------- #
def test_exclude_sectors_registered() -> None:
    assert get_rule("exclude_sectors") is ExcludeSectors


def test_exclude_sectors_pass_non_financial(benchmarks: IndustryBenchmarks) -> None:
    result = ExcludeSectors().evaluate(_company(industry="Software"), benchmarks)
    assert result.passed is True


def test_exclude_sectors_fail_bank(benchmarks: IndustryBenchmarks) -> None:
    result = ExcludeSectors().evaluate(_company(industry="Bank (Money Center)"), benchmarks)
    assert result.passed is False


def test_exclude_sectors_fail_insurance(benchmarks: IndustryBenchmarks) -> None:
    result = ExcludeSectors().evaluate(
        _company(industry="Insurance (Life)"), benchmarks
    )
    assert result.passed is False


def test_exclude_sectors_fail_on_is_financial_flag(
    benchmarks: IndustryBenchmarks,
) -> None:
    result = ExcludeSectors().evaluate(
        _company(industry="Software", is_financial_services=True), benchmarks
    )
    assert result.passed is False


def test_exclude_sectors_missing_industry_passes(
    benchmarks: IndustryBenchmarks,
) -> None:
    # No industry and not flagged: nothing to exclude on -> not eliminated here.
    result = ExcludeSectors().evaluate(_company(industry=None), benchmarks)
    assert result.passed is True


def test_exclude_sectors_configurable(benchmarks: IndustryBenchmarks) -> None:
    rule = ExcludeSectors(excluded=("Tobacco",))
    assert rule.evaluate(_company(industry="Tobacco"), benchmarks).passed is False
    # A default-excluded bank now passes because the custom list omits it.
    assert rule.evaluate(_company(industry="Bank"), benchmarks).passed is True


# --------------------------------------------------------------------------- #
# MaxNetDebtToEBITDA
# --------------------------------------------------------------------------- #
def test_max_net_debt_to_ebitda_registered() -> None:
    assert get_rule("max_net_debt_to_ebitda") is MaxNetDebtToEBITDA


def test_max_net_debt_to_ebitda_pass(benchmarks: IndustryBenchmarks) -> None:
    result = MaxNetDebtToEBITDA().evaluate(
        _company(net_debt=200.0, ebitda=100.0), benchmarks
    )
    assert result.passed is True


def test_max_net_debt_to_ebitda_fail(benchmarks: IndustryBenchmarks) -> None:
    result = MaxNetDebtToEBITDA().evaluate(
        _company(net_debt=500.0, ebitda=100.0), benchmarks
    )
    assert result.passed is False


def test_max_net_debt_to_ebitda_net_cash_passes(
    benchmarks: IndustryBenchmarks,
) -> None:
    # Negative net debt (net cash) trivially clears the leverage gate.
    result = MaxNetDebtToEBITDA().evaluate(
        _company(net_debt=-100.0, ebitda=100.0), benchmarks
    )
    assert result.passed is True


def test_max_net_debt_to_ebitda_missing_fails(benchmarks: IndustryBenchmarks) -> None:
    result = MaxNetDebtToEBITDA().evaluate(_company(net_debt=200.0), benchmarks)
    assert result.passed is False
    assert "unavailable" in result.reason


def test_max_net_debt_to_ebitda_nonpositive_ebitda_fails(
    benchmarks: IndustryBenchmarks,
) -> None:
    # Net debt with zero/negative EBITDA: leverage is undefined/infinite -> fail,
    # unless the company is in net cash (handled above).
    result = MaxNetDebtToEBITDA().evaluate(
        _company(net_debt=200.0, ebitda=0.0), benchmarks
    )
    assert result.passed is False


def test_max_net_debt_to_ebitda_configurable(benchmarks: IndustryBenchmarks) -> None:
    result = MaxNetDebtToEBITDA(maximum=6.0).evaluate(
        _company(net_debt=500.0, ebitda=100.0), benchmarks
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# MinInterestCoverage
# --------------------------------------------------------------------------- #
def test_min_interest_coverage_registered() -> None:
    assert get_rule("min_interest_coverage") is MinInterestCoverage


def test_min_interest_coverage_pass(benchmarks: IndustryBenchmarks) -> None:
    result = MinInterestCoverage().evaluate(
        _company(ebit=300.0, interest_expense=100.0), benchmarks
    )
    assert result.passed is True


def test_min_interest_coverage_fail(benchmarks: IndustryBenchmarks) -> None:
    result = MinInterestCoverage().evaluate(
        _company(ebit=150.0, interest_expense=100.0), benchmarks
    )
    assert result.passed is False


def test_min_interest_coverage_no_interest_passes(
    benchmarks: IndustryBenchmarks,
) -> None:
    # No interest expense -> coverage is effectively infinite -> clears the gate.
    result = MinInterestCoverage().evaluate(
        _company(ebit=10.0, interest_expense=0.0), benchmarks
    )
    assert result.passed is True


def test_min_interest_coverage_missing_fails(benchmarks: IndustryBenchmarks) -> None:
    result = MinInterestCoverage().evaluate(
        _company(interest_expense=100.0), benchmarks
    )
    assert result.passed is False
    assert "unavailable" in result.reason


def test_min_interest_coverage_configurable(benchmarks: IndustryBenchmarks) -> None:
    result = MinInterestCoverage(minimum=1.0).evaluate(
        _company(ebit=150.0, interest_expense=100.0), benchmarks
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# PositiveOperatingCashflow
# --------------------------------------------------------------------------- #
def test_positive_operating_cashflow_registered() -> None:
    assert get_rule("positive_operating_cashflow") is PositiveOperatingCashflow


def test_positive_operating_cashflow_pass(benchmarks: IndustryBenchmarks) -> None:
    # 5 of last 5 positive.
    history = (10.0, 20.0, 15.0, 12.0, 18.0)
    result = PositiveOperatingCashflow().evaluate(
        _company(operating_cashflow_history=history), benchmarks
    )
    assert result.passed is True


def test_positive_operating_cashflow_pass_with_one_bad_year(
    benchmarks: IndustryBenchmarks,
) -> None:
    # 4 of last 5 positive clears the default.
    history = (-5.0, 20.0, 15.0, 12.0, 18.0)
    result = PositiveOperatingCashflow().evaluate(
        _company(operating_cashflow_history=history), benchmarks
    )
    assert result.passed is True


def test_positive_operating_cashflow_fail(benchmarks: IndustryBenchmarks) -> None:
    # Only 3 of last 5 positive.
    history = (-5.0, -2.0, 15.0, 12.0, 18.0)
    result = PositiveOperatingCashflow().evaluate(
        _company(operating_cashflow_history=history), benchmarks
    )
    assert result.passed is False


def test_positive_operating_cashflow_uses_last_five_only(
    benchmarks: IndustryBenchmarks,
) -> None:
    # Older negatives outside the 5-year window must not count against the company.
    history = (-9.0, -9.0, -9.0, 10.0, 20.0, 15.0, 12.0, 18.0)
    result = PositiveOperatingCashflow().evaluate(
        _company(operating_cashflow_history=history), benchmarks
    )
    assert result.passed is True


def test_positive_operating_cashflow_insufficient_history_fails(
    benchmarks: IndustryBenchmarks,
) -> None:
    result = PositiveOperatingCashflow().evaluate(
        _company(operating_cashflow_history=(10.0, 20.0)), benchmarks
    )
    assert result.passed is False
    assert "insufficient" in result.reason


def test_positive_operating_cashflow_configurable(
    benchmarks: IndustryBenchmarks,
) -> None:
    # Require only 3 of last 5; a company with 3 positive now passes.
    history = (-5.0, -2.0, 15.0, 12.0, 18.0)
    result = PositiveOperatingCashflow(min_positive=3).evaluate(
        _company(operating_cashflow_history=history), benchmarks
    )
    assert result.passed is True


# --------------------------------------------------------------------------- #
# MaxGoodwillToAssets
# --------------------------------------------------------------------------- #
def test_max_goodwill_to_assets_registered() -> None:
    assert get_rule("max_goodwill_to_assets") is MaxGoodwillToAssets


def test_max_goodwill_to_assets_pass(benchmarks: IndustryBenchmarks) -> None:
    result = MaxGoodwillToAssets().evaluate(
        _company(goodwill=100.0, total_assets=1000.0), benchmarks
    )
    assert result.passed is True


def test_max_goodwill_to_assets_fail(benchmarks: IndustryBenchmarks) -> None:
    result = MaxGoodwillToAssets().evaluate(
        _company(goodwill=600.0, total_assets=1000.0), benchmarks
    )
    assert result.passed is False


def test_max_goodwill_to_assets_no_goodwill_passes(
    benchmarks: IndustryBenchmarks,
) -> None:
    result = MaxGoodwillToAssets().evaluate(
        _company(goodwill=0.0, total_assets=1000.0), benchmarks
    )
    assert result.passed is True


def test_max_goodwill_to_assets_missing_fails(benchmarks: IndustryBenchmarks) -> None:
    result = MaxGoodwillToAssets().evaluate(_company(goodwill=100.0), benchmarks)
    assert result.passed is False
    assert "unavailable" in result.reason


def test_max_goodwill_to_assets_zero_assets_fails(
    benchmarks: IndustryBenchmarks,
) -> None:
    result = MaxGoodwillToAssets().evaluate(
        _company(goodwill=100.0, total_assets=0.0), benchmarks
    )
    assert result.passed is False


def test_max_goodwill_to_assets_configurable(benchmarks: IndustryBenchmarks) -> None:
    result = MaxGoodwillToAssets(maximum=0.7).evaluate(
        _company(goodwill=600.0, total_assets=1000.0), benchmarks
    )
    assert result.passed is True
