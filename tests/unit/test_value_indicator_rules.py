from bot.screener.rules import (
    CompanyData,
    EVEBITDABelowIndustryMultiple,
    FCFYieldAbove,
    IndustryBenchmarks,
    PBVBelowIndustryMultipleWithROEAboveMedian,
    PEBelowIndustryMultiple,
    get_rule,
)

_BENCHMARKS = IndustryBenchmarks(
    industry="Software",
    pe=20.0,
    ev_ebitda=15.0,
    pbv=4.0,
    roe=0.15,
)

_NO_SECTOR = IndustryBenchmarks()  # all fields None


# --- PEBelowIndustryMultiple ---


def test_pe_below_passes_when_cheap() -> None:
    rule = PEBelowIndustryMultiple(multiple=0.7)
    company = CompanyData(ticker="AAPL", pe_ratio=12.0)  # 12 <= 0.7 * 20 = 14
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True
    assert result.score > 0.0
    assert "pe_ratio" in result.reason


def test_pe_below_fails_when_expensive() -> None:
    rule = PEBelowIndustryMultiple(multiple=0.7)
    company = CompanyData(ticker="AAPL", pe_ratio=18.0)  # 18 > 14
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert ">" in result.reason


def test_pe_below_no_sector_data() -> None:
    rule = PEBelowIndustryMultiple()
    company = CompanyData(ticker="AAPL", pe_ratio=12.0)
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is False
    assert result.reason == "no_sector_data"


def test_pe_below_no_company_pe() -> None:
    rule = PEBelowIndustryMultiple()
    company = CompanyData(ticker="AAPL")
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


# --- EVEBITDABelowIndustryMultiple ---


def test_ev_ebitda_below_passes_when_cheap() -> None:
    rule = EVEBITDABelowIndustryMultiple(multiple=0.7)
    company = CompanyData(ticker="MSFT", ev_ebitda=9.0)  # 9 <= 0.7 * 15 = 10.5
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True
    assert result.score > 0.0


def test_ev_ebitda_below_fails_when_expensive() -> None:
    rule = EVEBITDABelowIndustryMultiple(multiple=0.7)
    company = CompanyData(ticker="MSFT", ev_ebitda=12.0)  # 12 > 10.5
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0


def test_ev_ebitda_below_no_sector_data() -> None:
    rule = EVEBITDABelowIndustryMultiple()
    company = CompanyData(ticker="MSFT", ev_ebitda=9.0)
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is False
    assert result.reason == "no_sector_data"


def test_ev_ebitda_below_no_company_value() -> None:
    rule = EVEBITDABelowIndustryMultiple()
    company = CompanyData(ticker="MSFT")
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


# --- PBVBelowIndustryMultipleWithROEAboveMedian ---


def test_pbv_roe_passes_when_cheap_and_quality() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian(pbv_multiple=0.7)
    # pbv 2.5 <= 0.7*4=2.8, roe 20% >= 15%
    company = CompanyData(ticker="GOOG", pbv=2.5, roe=0.20)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is True
    assert result.score > 0.0


def test_pbv_roe_fails_when_pbv_expensive() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian(pbv_multiple=0.7)
    company = CompanyData(ticker="GOOG", pbv=3.5, roe=0.20)  # pbv 3.5 > 2.8
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "pbv" in result.reason


def test_pbv_roe_fails_when_roe_below_median() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian(pbv_multiple=0.7)
    company = CompanyData(ticker="GOOG", pbv=2.5, roe=0.10)  # roe 10% < 15%
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert result.score == 0.0
    assert "roe" in result.reason


def test_pbv_roe_no_sector_data() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian()
    company = CompanyData(ticker="GOOG", pbv=2.5, roe=0.20)
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is False
    assert result.reason == "no_sector_data"


def test_pbv_roe_no_company_pbv() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian()
    company = CompanyData(ticker="GOOG", roe=0.20)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


def test_pbv_roe_no_company_roe() -> None:
    rule = PBVBelowIndustryMultipleWithROEAboveMedian()
    company = CompanyData(ticker="GOOG", pbv=2.5)
    result = rule.evaluate(company, _BENCHMARKS)
    assert result.passed is False
    assert "not available" in result.reason


# --- FCFYieldAbove ---


def test_fcf_yield_passes_above_threshold() -> None:
    rule = FCFYieldAbove(min_yield=0.08)
    company = CompanyData(ticker="META", fcf_yield=0.10)
    result = rule.evaluate(company, _NO_SECTOR)  # no sector data needed
    assert result.passed is True
    assert result.score > 0.0
    assert ">=" in result.reason


def test_fcf_yield_fails_below_threshold() -> None:
    rule = FCFYieldAbove(min_yield=0.08)
    company = CompanyData(ticker="META", fcf_yield=0.05)
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is False
    assert result.score == 0.0
    assert "<" in result.reason


def test_fcf_yield_no_sector_data_still_evaluates() -> None:
    # FCFYieldAbove does not need sector benchmarks; missing sector data is irrelevant
    rule = FCFYieldAbove(min_yield=0.08)
    company = CompanyData(ticker="META", fcf_yield=0.12)
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is True


def test_fcf_yield_no_company_fcf() -> None:
    rule = FCFYieldAbove()
    company = CompanyData(ticker="META")
    result = rule.evaluate(company, _NO_SECTOR)
    assert result.passed is False
    assert "not available" in result.reason


# --- Registry ---


def test_all_value_rules_registered() -> None:
    assert get_rule("pe_below_industry_multiple") is PEBelowIndustryMultiple
    assert get_rule("ev_ebitda_below_industry_multiple") is EVEBITDABelowIndustryMultiple
    assert (
        get_rule("pbv_below_industry_multiple_with_roe_above_median")
        is PBVBelowIndustryMultipleWithROEAboveMedian
    )
    assert get_rule("fcf_yield_above") is FCFYieldAbove
