import pytest

from bot.screener.rules import (
    _REGISTRY,
    CompanyData,
    ExcludeSectors,
    IndustryBenchmarks,
    MarketCapMin,
    MaxGoodwillToAssets,
    MaxNetDebtToEBITDA,
    MinInterestCoverage,
    MinMarketCap,
    MinYearsHistory,
    PositiveOperatingCashflow,
    Rule,
    RuleResult,
    get_rule,
    register,
)

_FIXTURE_COMPANY = CompanyData(ticker="AAPL", market_cap=3_000_000_000_000.0)
_EMPTY_BENCHMARKS = IndustryBenchmarks()


# --- MarketCapMin ---


def test_market_cap_min_passes_large_company() -> None:
    rule = MarketCapMin(min_market_cap=1_000_000_000.0)
    result = rule.evaluate(_FIXTURE_COMPANY, _EMPTY_BENCHMARKS)
    assert result.passed is True
    assert 0.0 < result.score <= 1.0
    assert ">=" in result.reason


def test_market_cap_min_fails_small_company() -> None:
    rule = MarketCapMin(min_market_cap=1_000_000_000.0)
    tiny = CompanyData(ticker="TINY", market_cap=500_000.0)
    result = rule.evaluate(tiny, _EMPTY_BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "<" in result.reason


def test_market_cap_min_fails_when_market_cap_none() -> None:
    rule = MarketCapMin()
    result = rule.evaluate(CompanyData(ticker="UNKN"), _EMPTY_BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "not available" in result.reason


def test_rule_result_fields() -> None:
    r = RuleResult(passed=True, score=0.5, reason="ok")
    assert r.passed is True
    assert r.score == 0.5
    assert r.reason == "ok"


# --- Registry ---


def test_market_cap_min_is_registered() -> None:
    assert get_rule("market_cap_min") is MarketCapMin


def test_get_rule_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError, match="no_such_rule"):
        get_rule("no_such_rule")


def test_register_rejects_duplicate() -> None:
    class _Dupe(Rule):
        name = "market_cap_min"

        def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
            return RuleResult(passed=True, score=1.0, reason="dupe")

    with pytest.raises(ValueError, match="already registered"):
        register(_Dupe)


def test_register_and_lookup_new_rule() -> None:
    class _TestRule(Rule):
        name = "test_rule_xyz"

        def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
            return RuleResult(passed=True, score=1.0, reason="test")

    register(_TestRule)
    try:
        assert get_rule("test_rule_xyz") is _TestRule
    finally:
        del _REGISTRY["test_rule_xyz"]


_BENCHMARKS = IndustryBenchmarks()


# --- MinMarketCap ---


def test_min_market_cap_passes() -> None:
    rule = MinMarketCap()
    company = CompanyData(ticker="BIG", market_cap=200_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True
    assert result.score == 1.0


def test_min_market_cap_fails() -> None:
    rule = MinMarketCap()
    company = CompanyData(ticker="TINY", market_cap=50_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0


def test_min_market_cap_fails_when_none() -> None:
    result = MinMarketCap().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_min_market_cap_is_registered() -> None:
    assert get_rule("min_market_cap") is MinMarketCap


# --- MinYearsHistory ---


def test_min_years_history_passes() -> None:
    rule = MinYearsHistory()
    company = CompanyData(ticker="OLD", years_history=10)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True


def test_min_years_history_fails() -> None:
    rule = MinYearsHistory()
    company = CompanyData(ticker="NEW", years_history=2)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0


def test_min_years_history_fails_when_none() -> None:
    result = MinYearsHistory().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_min_years_history_is_registered() -> None:
    assert get_rule("min_years_history") is MinYearsHistory


# --- ExcludeSectors ---


def test_exclude_sectors_passes_for_allowed_sector() -> None:
    rule = ExcludeSectors()
    company = CompanyData(ticker="AAPL", sector="Technology")
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True


def test_exclude_sectors_fails_for_banks() -> None:
    rule = ExcludeSectors()
    company = CompanyData(ticker="JPM", sector="Banks")
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0


def test_exclude_sectors_fails_for_insurance() -> None:
    rule = ExcludeSectors()
    company = CompanyData(ticker="MET", sector="Insurance")
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False


def test_exclude_sectors_fails_when_sector_none() -> None:
    result = ExcludeSectors().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_exclude_sectors_custom_list() -> None:
    rule = ExcludeSectors(excluded=["Utilities"])
    assert (
        ExcludeSectors().evaluate(CompanyData(ticker="UTL", sector="Utilities"), _BENCHMARKS).passed
        is True
    )
    assert rule.evaluate(CompanyData(ticker="UTL", sector="Utilities"), _BENCHMARKS).passed is False


def test_exclude_sectors_is_registered() -> None:
    assert get_rule("exclude_sectors") is ExcludeSectors


# --- MaxNetDebtToEBITDA ---


def test_max_net_debt_to_ebitda_passes() -> None:
    rule = MaxNetDebtToEBITDA()
    company = CompanyData(ticker="LOW", net_debt=2_000_000.0, ebitda=1_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True  # ratio = 2.0 <= 4.0


def test_max_net_debt_to_ebitda_fails() -> None:
    rule = MaxNetDebtToEBITDA()
    company = CompanyData(ticker="HIGH", net_debt=10_000_000.0, ebitda=1_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False  # ratio = 10.0 > 4.0
    assert result.score == 0.0


def test_max_net_debt_to_ebitda_fails_when_ebitda_zero() -> None:
    company = CompanyData(ticker="NEG", net_debt=1_000_000.0, ebitda=0.0)
    result = MaxNetDebtToEBITDA().evaluate(company, _BENCHMARKS)
    assert result.passed is False


def test_max_net_debt_to_ebitda_fails_when_missing() -> None:
    result = MaxNetDebtToEBITDA().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_max_net_debt_to_ebitda_is_registered() -> None:
    assert get_rule("max_net_debt_to_ebitda") is MaxNetDebtToEBITDA


# --- MinInterestCoverage ---


def test_min_interest_coverage_passes() -> None:
    rule = MinInterestCoverage()
    company = CompanyData(ticker="SAFE", ebit=1_000_000.0, interest_expense=400_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True  # ratio = 2.5 >= 2.0


def test_min_interest_coverage_fails() -> None:
    rule = MinInterestCoverage()
    company = CompanyData(ticker="RISK", ebit=100_000.0, interest_expense=500_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False  # ratio = 0.2 < 2.0
    assert result.score == 0.0


def test_min_interest_coverage_passes_no_leverage() -> None:
    company = CompanyData(ticker="NODEBT", ebit=1_000_000.0, interest_expense=0.0)
    result = MinInterestCoverage().evaluate(company, _BENCHMARKS)
    assert result.passed is True


def test_min_interest_coverage_fails_when_missing() -> None:
    result = MinInterestCoverage().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_min_interest_coverage_is_registered() -> None:
    assert get_rule("min_interest_coverage") is MinInterestCoverage


# --- PositiveOperatingCashflow ---


def test_positive_operating_cashflow_passes() -> None:
    rule = PositiveOperatingCashflow()
    # 4 of 5 years positive
    company = CompanyData(
        ticker="OK", operating_cashflow_history=[100.0, 200.0, -50.0, 300.0, 400.0]
    )
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True


def test_positive_operating_cashflow_fails() -> None:
    rule = PositiveOperatingCashflow()
    # Only 2 of 5 years positive
    company = CompanyData(
        ticker="BAD", operating_cashflow_history=[-100.0, -200.0, 50.0, -300.0, 400.0]
    )
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0


def test_positive_operating_cashflow_uses_last_n_years() -> None:
    rule = PositiveOperatingCashflow(min_positive_years=4, lookback_years=5)
    # 7 years; last 5 are all positive → should pass
    history = [-1.0, -1.0, 100.0, 200.0, 300.0, 400.0, 500.0]
    company = CompanyData(ticker="HIST", operating_cashflow_history=history)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True


def test_positive_operating_cashflow_fails_when_empty() -> None:
    result = PositiveOperatingCashflow().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_positive_operating_cashflow_is_registered() -> None:
    assert get_rule("positive_operating_cashflow") is PositiveOperatingCashflow


# --- MaxGoodwillToAssets ---


def test_max_goodwill_to_assets_passes() -> None:
    rule = MaxGoodwillToAssets()
    company = CompanyData(ticker="LOW", goodwill=300_000.0, total_assets=1_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True  # ratio = 0.3 <= 0.5


def test_max_goodwill_to_assets_fails() -> None:
    rule = MaxGoodwillToAssets()
    company = CompanyData(ticker="HIGH", goodwill=600_000.0, total_assets=1_000_000.0)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False  # ratio = 0.6 > 0.5
    assert result.score == 0.0


def test_max_goodwill_to_assets_fails_when_assets_zero() -> None:
    company = CompanyData(ticker="ZERO", goodwill=0.0, total_assets=0.0)
    result = MaxGoodwillToAssets().evaluate(company, _BENCHMARKS)
    assert result.passed is False


def test_max_goodwill_to_assets_fails_when_missing() -> None:
    result = MaxGoodwillToAssets().evaluate(CompanyData(ticker="UNKN"), _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_max_goodwill_to_assets_is_registered() -> None:
    assert get_rule("max_goodwill_to_assets") is MaxGoodwillToAssets
